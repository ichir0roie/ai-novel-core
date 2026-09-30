"""テスト用の道具。この下のモジュールは必ず `novel.test.db` を読み書きする。

`db.schema` は import 時に `DEM_DB_PATH`(と `DEM_DATABASE_URL`)で engine を固定するので、
この package の読み込み(= 配下のモジュールより先に走る)で環境変数を差し替える。
"""
import os
import sqlite3
import sys

TEST_DB_PATH = os.path.join(os.environ["DEM_WORLD_DIR"], "novel.test.db")
# `db.schema` の NOVEL_DB_PATH と同じ決め方(schema はこの package より後に読むので、ここでは import できない)
NOVEL_DB_PATH = os.environ.get("DEM_NOVEL_DB_PATH", os.path.join(os.environ["DEM_WORLD_DIR"], "novel.db"))

if "db.schema" in sys.modules:
    loaded = os.path.abspath(sys.modules["db.schema"].DB_PATH)
    if loaded != os.path.abspath(TEST_DB_PATH) or sys.modules["db.schema"].DATABASE_URL:
        raise RuntimeError(
            f"db.schema が {sys.modules['db.schema'].DATABASE_URL or loaded} で先に読み込まれている。"
            f"tool.test 配下は {TEST_DB_PATH} しか使わないので、こちらを先に import する")

os.environ["DEM_DB_PATH"] = TEST_DB_PATH
# PostgreSQL の URL は DEM_DB_PATH より優先されるので、本番の db に書かないよう消す
os.environ.pop("DEM_DATABASE_URL", None)


def copy_novel_db(source_db_path: str = NOVEL_DB_PATH) -> None:
    """本番の db を写して novel.test.db を作る。写し元は読み取り専用で開く。"""
    if not os.path.exists(source_db_path):
        raise FileNotFoundError(f"写し元の db が無い: {source_db_path}")
    # ファイルのままコピーすると、他のセッションが書き込み中の db を半端に写すことがある
    source = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    target = sqlite3.connect(TEST_DB_PATH)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
