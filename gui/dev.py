#!/usr/bin/env python3
"""API(uvicorn)と画面(next dev)を一緒に起こし、ブラウザで画面を開く。Ctrl+C で両方止める。

世界リポジトリのルートから(`DEM_WORLD_DIR` / `PYTHONPATH` は他の python と同じ):

    .venv/bin/python -m gui.dev                 # http://localhost:3000 を開く
    .venv/bin/python -m gui.dev --no-browser    # 開かない
    .venv/bin/python -m gui.dev --api-port 8765 --web-port 3000
    .venv/bin/python -m gui.dev --browser-only  # API・画面は起こさず、ブラウザだけ開く(すでに起きている前提)

`gui/web/node_modules` が無ければ先に `npm install` を回す。
API には `CLAUDECODE=1` を渡すので、Claude Code の外から起こしても claude を叩く入口が通る。
ポートが既に使われていれば、それを聞いている処理(前回の起動の残りなど)を止めてから起こす。

ブラウザは Brave があればそれを使い、プロファイルを世界リポジトリのルート(`DEM_WORLD_DIR`)の
`.brave-profile/` に作って開く(普段のプロファイルと分け、GUI 用のタブ・設定だけをそこに残す)。
このディレクトリは Claude Code の SessionStart フック(`.claude/hooks/session-start.sh`)が
セッション開始時に用意する(`gui.dev` 実行時にも無ければ作る)。
Brave が無ければ既定のブラウザで開く。
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from data_access_logic.logs import configure_logging

# `python -m gui.dev` で起こすと `__name__` は `__main__` になるので、名前を書く
logger = logging.getLogger("gui.dev")

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAVE_PROFILE_DIR_NAME = ".brave-profile"


def _npm() -> str:
    # Windows の npm は `npm.cmd`。PATHEXT を見て実体に解決する
    return shutil.which("npm") or "npm"


def _brave() -> str | None:
    for name in ("brave-browser", "brave-browser-stable", "brave", "brave.exe"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _brave_profile_dir() -> str:
    world_dir = os.environ.get("DEM_WORLD_DIR") or os.getcwd()
    return os.path.join(os.path.abspath(world_dir), BRAVE_PROFILE_DIR_NAME)


def _open_browser(url: str) -> None:
    brave = _brave()
    if brave is None:
        logger.info("Brave が見つからないので既定のブラウザで開く")
        webbrowser.open(url)
        return
    profile = _brave_profile_dir()
    os.makedirs(profile, exist_ok=True)
    logger.info(f"Brave をプロファイル {profile} で開く")
    # Ctrl+C でサーバーを止めてもブラウザは残すため、プロセスグループを分けて起動だけする
    _popen([brave, f"--user-data-dir={profile}", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _http_alive(port: int, path: str = "/", timeout: float = 1.0) -> bool:
    # uvicorn --reload はワーカーの起動に失敗しても listen socket は監視役(reloader)側に
    # 残ったままなので、_port_open の TCP 接続だけでは死活が分からない。実際に応答が返るかで見る
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def _listening_pids(port: int) -> list[int]:
    if sys.platform.startswith("linux"):
        # lsof は環境によって node のソケットを列挙しない(next-server が見えなかった)ので、ss を使う
        result = subprocess.run(["ss", "-Hltnp", f"sport = :{port}"], capture_output=True, text=True)
        return sorted({int(pid) for pid in re.findall(r"pid=(\d+)", result.stdout)})
    if os.name == "posix":
        result = subprocess.run(["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
        return sorted({int(pid) for pid in result.stdout.split()})
    result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
    pids = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
            pids.add(int(parts[4]))
    return sorted(pids)


def _kill(pid: int, force: bool) -> None:
    if os.name != "posix":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        # uvicorn --reload は親(監視)と子(ポートを聞く)に分かれるので、自分のグループでなければまとめて止める
        if pgid != os.getpgid(0):
            os.killpg(pgid, sig)
        else:
            os.kill(pid, sig)
    except ProcessLookupError:
        return


def _wait_until_closed(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _port_open(port):
            return True
        time.sleep(0.2)
    return not _port_open(port)


def _free_port(port: int, name: str) -> bool:
    try:
        pids = _listening_pids(port)
    except FileNotFoundError as e:
        logger.warning(f"ポート {port}({name})を使っている処理を調べられない({e.filename} が無い)")
        return False
    if not pids:
        logger.warning(f"ポート {port}({name})を使っている処理が見つからない")
        return False
    logger.info(f"ポート {port}({name})を使っている処理 {pids} を止める")
    for pid in pids:
        _kill(pid, force=False)
    if _wait_until_closed(port, timeout=10.0):
        return True
    for pid in pids:
        _kill(pid, force=True)
    return _wait_until_closed(port, timeout=5.0)


# uvicorn --reload はワーカーの起動に失敗しても監視役(reloader)自体は生き続けるため、
# プロセスの生死だけを見ていると応答しないまま気付けない。応答が無い時間もあわせて見る
WATCH_INTERVAL = 20.0
STALL_TIMEOUT = 20.0


def _wait_for(port: int, name: str, process: subprocess.Popen, path: str = "/", timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            logger.warning(f"{name} が終了コード {process.returncode} で止まった")
            return False
        if _http_alive(port, path):
            return True
        time.sleep(0.3)
    logger.warning(f"{name} が {timeout:.0f} 秒で立ち上がらなかった")
    return False


def _popen(args: list[str], cwd: str | None = None, env: dict | None = None, **kwargs) -> subprocess.Popen:
    # 子をまとめて止められるよう、POSIX ではプロセスグループを分ける
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(args, cwd=cwd, env=env, **kwargs)


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.send_signal(signal.CTRL_BREAK_EVENT)
    except (ProcessLookupError, OSError):
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを開かない")
    parser.add_argument("--no-reload", action="store_true", help="uvicorn の自動再読み込みを切る")
    parser.add_argument("--browser-only", action="store_true",
                         help="ブラウザだけ開く(API・画面はすでに起きている前提で、起こしも死活監視もしない)")
    args = parser.parse_args(argv)
    configure_logging()

    if args.browser_only:
        _open_browser(f"http://localhost:{args.web_port}/")
        return 0

    for port, name in ((args.api_port, "API"), (args.web_port, "画面")):
        if _port_open(port) and not _free_port(port, name):
            logger.error(f"ポート {port}({name})を空けられない。手で止めるか --{'api' if name == 'API' else 'web'}-port で変える")
            return 1
    if not os.path.isdir(os.path.join(WEB_DIR, "node_modules")):
        logger.info("gui/web/node_modules が無いので npm install を回す")
        subprocess.run([_npm(), "install", "--no-audit", "--no-fund"], cwd=WEB_DIR, check=True)

    def spawn_api() -> subprocess.Popen:
        api_args = [sys.executable, "-m", "uvicorn", "gui.api.app:app", "--port", str(args.api_port)]
        if not args.no_reload:
            # 監視は core/ だけ。cwd(世界のルート)を丸ごと見ると .venv まで走査して重い
            api_args += ["--reload", "--reload-dir", CORE_DIR]
        # ユーザが素のターミナルから起こしても、claude を叩く入口(AI で作成など)を通す(gui/api/claude_env.py)
        return _popen(api_args, env={**os.environ, "CLAUDECODE": "1"})

    def spawn_web() -> subprocess.Popen:
        web_env = {**os.environ, "NOVEL_API_URL": f"http://127.0.0.1:{args.api_port}"}
        web_args = [_npm(), "run", "dev", "--", "--port", str(args.web_port)]
        return _popen(web_args, cwd=WEB_DIR, env=web_env)

    api: subprocess.Popen | None = None
    web: subprocess.Popen | None = None
    down_since: dict[str, float | None] = {"API": None, "画面": None}

    def watch(process: subprocess.Popen, port: int, name: str, spawn, path: str = "/") -> subprocess.Popen:
        # 片方が落ちてももう片方は止めず、落ちた方だけ自動で再起動する
        if process.poll() is not None:
            logger.warning(f"{name} が止まった(終了コード {process.returncode})。再起動する")
            process = spawn()
            _wait_for(port, name, process, path)
            down_since[name] = None
            return process
        if _http_alive(port, path):
            down_since[name] = None
            return process
        since = down_since[name]
        if since is None:
            down_since[name] = time.time()
        elif time.time() - since > STALL_TIMEOUT:
            logger.warning(f"{name} が応答しないまま {STALL_TIMEOUT:.0f} 秒止まっている"
                           "(reload 先のコードにエラーが残っている?)。作り直す")
            _terminate(process)
            process = spawn()
            _wait_for(port, name, process, path)
            down_since[name] = None
        return process

    # Ctrl+C(SIGINT)だけでなく、タスクの停止などの SIGTERM でも finally を通して両方止める
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    # 非対話の bash が `&` で裏に起こすと SIGINT を無視する設定を引き継ぎ、Python は KeyboardInterrupt を出さなくなる
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        api = spawn_api()
        web = spawn_web()
        if not (_wait_for(args.api_port, "API", api, "/api/health") and _wait_for(args.web_port, "画面", web)):
            return 1
        url = f"http://localhost:{args.web_port}/"
        logger.info(f"API http://127.0.0.1:{args.api_port}/docs / 画面 {url}(Ctrl+C で止める)")
        if not args.no_browser:
            _open_browser(url)
        while True:
            api = watch(api, args.api_port, "API", spawn_api, "/api/health")
            web = watch(web, args.web_port, "画面", spawn_web)
            time.sleep(WATCH_INTERVAL)
    except KeyboardInterrupt:
        logger.info("止める")
        return 0
    finally:
        for process in (api, web):
            if process is not None:
                _terminate(process)


if __name__ == "__main__":
    sys.exit(main())
