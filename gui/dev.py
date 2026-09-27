#!/usr/bin/env python3
"""API(uvicorn)と画面(next dev)を一緒に起こし、ブラウザで画面を開く。Ctrl+C で両方止める。

世界リポジトリのルートから(`DEM_WORLD_DIR` / `PYTHONPATH` は他の python と同じ):

    .venv/bin/python -m gui.dev                 # http://localhost:3000 を開く
    .venv/bin/python -m gui.dev --no-browser    # 開かない
    .venv/bin/python -m gui.dev --api-port 8765 --web-port 3000

`gui/web/node_modules` が無ければ先に `npm install` を回す。
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _npm() -> str:
    # Windows の npm は `npm.cmd`。PATHEXT を見て実体に解決する
    return shutil.which("npm") or "npm"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for(port: int, name: str, process: subprocess.Popen, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            print(f"[gui/dev] {name} が終了コード {process.returncode} で止まった", file=sys.stderr)
            return False
        if _port_open(port):
            return True
        time.sleep(0.3)
    print(f"[gui/dev] {name} が {timeout:.0f} 秒で立ち上がらなかった", file=sys.stderr)
    return False


def _popen(args: list[str], cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    # 子をまとめて止められるよう、POSIX ではプロセスグループを分ける
    kwargs = {}
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを開かない")
    parser.add_argument("--no-reload", action="store_true", help="uvicorn の自動再読み込みを切る")
    args = parser.parse_args(argv)

    for port, name in ((args.api_port, "API"), (args.web_port, "画面")):
        if _port_open(port):
            print(f"[gui/dev] ポート {port}({name})は既に使われている。先に止めるか --{'api' if name == 'API' else 'web'}-port で変える",
                  file=sys.stderr)
            return 1
    if not os.path.isdir(os.path.join(WEB_DIR, "node_modules")):
        print("[gui/dev] gui/web/node_modules が無いので npm install を回す")
        subprocess.run([_npm(), "install", "--no-audit", "--no-fund"], cwd=WEB_DIR, check=True)

    api_args = [sys.executable, "-m", "uvicorn", "gui.api.app:app", "--port", str(args.api_port)]
    if not args.no_reload:
        api_args.append("--reload")
    web_env = {**os.environ, "NOVEL_API_URL": f"http://127.0.0.1:{args.api_port}"}
    web_args = [_npm(), "run", "dev", "--", "--port", str(args.web_port)]

    processes = []
    # Ctrl+C(SIGINT)だけでなく、タスクの停止などの SIGTERM でも finally を通して両方止める
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        api = _popen(api_args)
        processes.append(api)
        web = _popen(web_args, cwd=WEB_DIR, env=web_env)
        processes.append(web)
        if not (_wait_for(args.api_port, "API", api) and _wait_for(args.web_port, "画面", web)):
            return 1
        url = f"http://localhost:{args.web_port}/"
        print(f"[gui/dev] API http://127.0.0.1:{args.api_port}/docs / 画面 {url}(Ctrl+C で止める)")
        if not args.no_browser:
            webbrowser.open(url)
        while True:
            for process, name in ((api, "API"), (web, "画面")):
                if process.poll() is not None:
                    print(f"[gui/dev] {name} が止まった(終了コード {process.returncode})。もう片方も止める", file=sys.stderr)
                    return process.returncode or 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[gui/dev] 止める")
        return 0
    finally:
        for process in processes:
            _terminate(process)


if __name__ == "__main__":
    sys.exit(main())
