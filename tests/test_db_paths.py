"""db の置き場所。テストは novel.test.db、本番の入口は世界リポジトリの novel.db を向くこと。"""
import os
import subprocess
import sys

from db.schema import NOVEL_DB_PATH, get_env_session, get_novel_session, get_test_session


def test_fixed_sessions_ignore_env_db_path():
    def db_file(factory):
        with factory() as s:
            return os.path.basename(s.get_bind().url.database)

    assert db_file(get_env_session) == "novel.test.db"
    assert db_file(get_test_session) == "novel.test.db"
    assert db_file(get_novel_session) == "novel.db"


def test_novel_db_lives_in_parent_world_repo():
    world_dir = os.environ["DEM_WORLD_DIR"]
    assert os.path.normpath(NOVEL_DB_PATH) == os.path.normpath(os.path.join(world_dir, "novel.db"))


def test_novel_db_path_follows_env(tmp_path):
    env = dict(os.environ, DEM_NOVEL_DB_PATH=str(tmp_path / "a.db"))
    code = ("from db.schema import NOVEL_DB_PATH, get_novel_session;"
            "print(NOVEL_DB_PATH); print(get_novel_session().get_bind().url.database)")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out == [str(tmp_path / "a.db"), str(tmp_path / "a.db")]
