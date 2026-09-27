"""API と画面を一緒に起こす `gui.dev`。サーバーは起こさず、起こす前の確かめだけを見る。"""
import socket
import subprocess
import sys

from gui import dev


def _free_port_number() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_frees_a_port_by_stopping_the_process_listening_on_it():
    port = _free_port_number()
    listener = subprocess.Popen(
        [sys.executable, "-c",
         f"import socket, time; s = socket.socket(); s.bind(('127.0.0.1', {port})); s.listen(1); time.sleep(60)"],
        start_new_session=True,
    )
    try:
        assert dev._wait_for(port, "listener", listener, timeout=10)
        assert dev._free_port(port, "API") is True
        assert dev._port_open(port) is False
        assert listener.wait(timeout=5) != 0
    finally:
        if listener.poll() is None:
            listener.kill()


def test_free_port_reports_when_nothing_is_listening(capsys):
    port = _free_port_number()
    assert dev._free_port(port, "API") is False
    assert f"ポート {port}" in capsys.readouterr().err


def test_refuses_when_a_port_cannot_be_freed(monkeypatch, capsys):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        monkeypatch.setattr(dev, "_free_port", lambda port, name: False)
        assert dev.main(["--api-port", str(port), "--no-browser"]) == 1
    assert f"ポート {port}" in capsys.readouterr().err


def test_brave_profile_dir_is_under_world_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DEM_WORLD_DIR", str(tmp_path))
    assert dev._brave_profile_dir() == str(tmp_path / dev.BRAVE_PROFILE_DIR_NAME)


def test_open_browser_launches_brave_with_repo_local_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("DEM_WORLD_DIR", str(tmp_path))
    monkeypatch.setattr(dev, "_brave", lambda: "/usr/bin/brave-browser")
    launched = []
    monkeypatch.setattr(dev, "_popen", lambda args, **kwargs: launched.append(args))
    monkeypatch.setattr(dev.webbrowser, "open", lambda url: (_ for _ in ()).throw(AssertionError("既定のブラウザで開いてはいけない")))

    dev._open_browser("http://localhost:3000/")

    profile = tmp_path / dev.BRAVE_PROFILE_DIR_NAME
    assert profile.is_dir()
    assert launched == [["/usr/bin/brave-browser", f"--user-data-dir={profile}", "http://localhost:3000/"]]


def test_open_browser_falls_back_to_default_browser_without_brave(monkeypatch, tmp_path):
    monkeypatch.setenv("DEM_WORLD_DIR", str(tmp_path))
    monkeypatch.setattr(dev, "_brave", lambda: None)
    monkeypatch.setattr(dev, "_popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Brave を起動してはいけない")))
    opened = []
    monkeypatch.setattr(dev.webbrowser, "open", lambda url: opened.append(url))

    dev._open_browser("http://localhost:3000/")

    assert opened == ["http://localhost:3000/"]
    assert not (tmp_path / dev.BRAVE_PROFILE_DIR_NAME).exists()
