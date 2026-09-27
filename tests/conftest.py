"""テストは `novel.test.db` だけを読み書きする。`tool.test` を最初に import して db パスを固定する。"""
import os

import pytest

from tool.test import TEST_DB_PATH  # noqa: F401  schema より先に読む(db を novel.test.db に固定)
from db.schema import Base, create_db, engine, get_env_session  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(Engine, "connect")
def _fast_sqlite(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA synchronous=OFF")
    cursor.execute("PRAGMA journal_mode=MEMORY")
    cursor.close()


@pytest.fixture(scope="session", autouse=True)
def fresh_test_db():
    # create_db が返す engine も捨てる。消して作り直したファイルを掴んだまま
    # 残ると、以後の書き込みが sqlite の disk I/O error になることがある
    create_db(TEST_DB_PATH).dispose()
    engine.dispose()  # 作り直す前のファイルを掴んでいる接続を捨てる
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture(autouse=True)
def no_real_claude_calls(monkeypatch):
    """`ai.claude_code.ai_client` は `claude -p` を実際に叩くので、既定では空の辞書
    (失敗扱い)を返すよう塞ぐ。応答の中身を見るテストは、自分で `try_generate_json` を上書きする。"""
    from ai.claude_code import ai_client
    monkeypatch.setattr(ai_client, "try_generate_json", lambda *a, **k: {})


@pytest.fixture
def session():
    with get_env_session() as s:
        yield s
