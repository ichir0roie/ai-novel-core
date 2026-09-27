"""API と画面を一緒に起こす `gui.dev`。サーバーは起こさず、起こす前の確かめだけを見る。"""
import socket

from gui import dev


def test_refuses_when_a_port_is_already_in_use(capsys):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert dev._port_open(port) is True
        assert dev.main(["--api-port", str(port), "--no-browser"]) == 1
    assert f"ポート {port}" in capsys.readouterr().err
    assert dev._port_open(port) is False
