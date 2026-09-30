"""テスト用の道具。この下のモジュールは必ず、手元の PostGIS のテスト用の db(`novel_test`)を読み書きする。

`db.schema` は import 時に `DEM_DATABASE_URL` で engine を固定するので、この package の読み込み(= 配下のモジュールより先に走る)で
環境変数を差し替える。差し替える前の `DEM_DATABASE_URL`(手元は転送越しの RDS)は、本番を写すときの写し元として取っておく。
"""
import os
import sys

from sqlalchemy.engine import make_url

TEST_DATABASE_NAME = "novel_test"
PRODUCTION_DATABASE_URL = os.environ.get("DEM_DATABASE_URL") or None
PRODUCTION_IAM_AUTH = os.environ.get("DEM_DATABASE_IAM_AUTH") == "1"


def _test_database_url() -> str:
    dev = os.environ.get("DEM_DEV_DATABASE_URL")
    if not dev:
        raise RuntimeError("DEM_DEV_DATABASE_URL が無い。手元の PostGIS を infra_local/postgis.sh で用意する"
                           "(SessionStart フックが用意して渡す)")
    url = make_url(dev).set(database=TEST_DATABASE_NAME)
    # 取り違えて本番(転送越しの RDS も 127.0.0.1)に書かないよう、開発用の db と同じサーバーの別の db だけを許す
    if url.host not in ("127.0.0.1", "localhost") or PRODUCTION_DATABASE_URL and \
            (make_url(PRODUCTION_DATABASE_URL).host, make_url(PRODUCTION_DATABASE_URL).port) == (url.host, url.port):
        raise RuntimeError(f"テスト用の db が手元の PostGIS を指していない: {url.render_as_string(hide_password=True)}")
    return url.render_as_string(hide_password=False)


TEST_DATABASE_URL = _test_database_url()

if "db.schema" in sys.modules and sys.modules["db.schema"].DATABASE_URL != TEST_DATABASE_URL:
    raise RuntimeError("db.schema がテスト用の db 以外で先に読み込まれている。tool.test 配下は "
                       f"{TEST_DATABASE_NAME} しか使わないので、こちらを先に import する")

os.environ["DEM_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.pop("DEM_DATABASE_IAM_AUTH", None)


def copy_production_db() -> None:
    """テスト用の db を作り直し、本番の db の行を写す。写し元は読むだけ。"""
    if not PRODUCTION_DATABASE_URL:
        raise RuntimeError("写し元の DEM_DATABASE_URL が無い。`tool.aws.rds --serve` の転送を張り、RDS への URL を渡しておく")
    from sqlalchemy import text

    from db.postgres import init_db
    from db.postgres.copy_db import copy_database
    from db.schema import engine, make_url_engine

    engine.dispose()
    admin = make_url_engine(make_url(TEST_DATABASE_URL).set(database="postgres").render_as_string(hide_password=False))
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)'))
    admin.dispose()
    init_db.main(["--url", TEST_DATABASE_URL, "--create-database"])

    source = make_url_engine(PRODUCTION_DATABASE_URL, iam_auth=PRODUCTION_IAM_AUTH)
    try:
        copy_database(source, engine)
    finally:
        source.dispose()
