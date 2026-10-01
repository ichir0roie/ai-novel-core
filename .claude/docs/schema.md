# schema の確認方法

- 列の定義は `db/schema.py` が唯一の正。列名・型を確かめたいときは `sqlite_master` へクエリを打たず、この `db/schema.py` を Read する。
- マイグレーションは `db/alembic/`。コマンド例は `db/alembic/README` にある。
- `schema.py` を変えたら alembic の `revision --autogenerate` → 内容確認 → `upgrade head` の順(手元の開発用の db に当てる)。
  AWS の db へは、`main` へのマージで CI が当てる(`.docs/ci-cd.md` の「マイグレーション」)。列を消す変更は、マージから API の差し替えまでの 1〜2 分だけ古い API が失敗しうる
- SQLite と PostgreSQL の両方で通る書き方にする。NULL を持てる列で並べるときは NULL の向き(降順は `.nulls_last()`)を明示し、
  `DISTINCT` の結果を順番どおりに使うなら `order_by` を付ける。PostgreSQL にだけある PostGIS の列は `db/postgres/postgis.py`(`.docs/postgres.md`)
