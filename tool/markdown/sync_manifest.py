#!/usr/bin/env python3
"""md と db のどちらが前回の同期から変わったかを、ファイルごとのハッシュで見分ける。

台帳には md の相対パスごとに、同期した時点の md の中身(`md`)と、
その行を db から書き出した中身(`db`)のハッシュを持つ。
今の md が `md` と違えば手で直された md、今の行を書き出した中身が `db` と違えば
db 側で直された行とみなす。
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import time

MANIFEST_NAME = ".markdown_sync.json"
LOCK_NAME = ".markdown_sync.lock"

# 落ちたプロセスが残したロックを、この秒数より古ければ捨てる
LOCK_STALE_SECONDS = 600

__all__ = [
    "MANIFEST_NAME", "LOCK_NAME", "SyncLockedError", "Manifest",
    "manifest_path", "digest", "read_text", "locked",
]


class SyncLockedError(RuntimeError):
    pass


def _beside(root: str, name: str) -> str:
    # 台帳とロックは `root` の外に置く。`root` の中は md の写しだけにしておきたいため
    return os.path.join(os.path.dirname(os.path.abspath(root)), name)


def manifest_path(root: str) -> str:
    return _beside(root, MANIFEST_NAME)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: str) -> str:
    # 改行は読むときに \n へ揃える(Windows で書いた md は CRLF になっている)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _rename_legacy_tables(entries: dict[str, dict]) -> None:
    # 話の枠 episode → plot、本文 episode_text → episode の改名より前の台帳を読み替える。
    # 台帳は git に載らないので、改名済みの db だけが pull で届き、マイグレーションが台帳に回らないことがある。
    # 枠は .md・本文は .txt なので、古い "episode" はパスの拡張子で枠と決まる
    for key, entry in entries.items():
        if entry["table"] == "episode" and key.endswith(".md"):
            entry["table"] = "plot"
        elif entry["table"] == "episode_text":
            entry["table"] = "episode"


class Manifest:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        path = manifest_path(root)
        self.exists = os.path.exists(path)
        self.entries: dict[str, dict] = {}
        if self.exists:
            with open(path, encoding="utf-8") as f:
                self.entries = json.load(f)
            _rename_legacy_tables(self.entries)

    def key(self, path: str) -> str:
        return os.path.relpath(os.path.abspath(path), self.root).replace(os.sep, "/")

    def get(self, path: str) -> dict | None:
        return self.entries.get(self.key(path))

    def set(self, path: str, table: str, row_id: int, md: str, db: str) -> None:
        self.entries[self.key(path)] = {"table": table, "id": row_id, "md": md, "db": db}

    def drop(self, path: str) -> None:
        self.entries.pop(self.key(path), None)

    def edited(self, path: str, text: str) -> bool:
        entry = self.get(path)
        return entry is None or entry["md"] != digest(text)

    def missing(self) -> list[str]:
        """前回の同期より後に消された(または動かされた)md のパス。"""
        paths = [os.path.normpath(os.path.join(self.root, key)) for key in self.entries]
        return sorted(path for path in paths if not os.path.exists(path))

    def save(self) -> None:
        path = manifest_path(self.root)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(self.entries.items())), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        self.exists = True


@contextmanager
def locked(root: str, timeout: float = 300.0):
    """同じ `root` の同期を、セッションをまたいで一度に一つだけ走らせる。"""
    path = _beside(root, LOCK_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.stat(path).st_mtime > LOCK_STALE_SECONDS:
                    os.remove(path)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise SyncLockedError(
                    f"{path} を他の同期が握ったまま {timeout:.0f} 秒たった。"
                    "他のセッションの同期が終わるのを待つ。落ちたプロセスの残りなら消してよい")
            time.sleep(0.5)
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        yield
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
