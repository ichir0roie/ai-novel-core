"""テスト用の道具。この下のモジュールは必ず `novel.test.db` を読み書きする。

`db.schema` は import 時に `DEM_DB_PATH` で engine を固定するので、
この package の読み込み(= 配下のモジュールより先に走る)で環境変数を差し替える。
"""
import os
import sys

TEST_DB_PATH = os.path.join(os.environ["DEM_WORLD_DIR"], "novel.test.db")

if "db.schema" in sys.modules:
    loaded = os.path.abspath(sys.modules["db.schema"].DB_PATH)
    if loaded != os.path.abspath(TEST_DB_PATH):
        raise RuntimeError(
            f"db.schema が {loaded} で先に読み込まれている。"
            f"tool.test 配下は {TEST_DB_PATH} しか使わないので、こちらを先に import する")

os.environ["DEM_DB_PATH"] = TEST_DB_PATH
# DEM_DATABASE_URL(RDS など)があるとそちらが優先されてしまうので、テストは常に sqlite に落とす
os.environ.pop("DEM_DATABASE_URL", None)
