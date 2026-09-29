# schema の確認方法

- 列の定義は `db/schema.py` が唯一の正。列名・型を確かめたいときは `sqlite_master` へクエリを打たず、この `db/schema.py` を Read する。
- マイグレーションは `db/alembic/`。コマンド例は `db/alembic/README` にある。
- `schema.py` を変えたら alembic の `revision --autogenerate` → 内容確認 → `upgrade head` の順。
