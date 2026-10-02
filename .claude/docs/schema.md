# schema の確認方法

- 列の定義は `db/schema.py` が唯一の正。列名・型は db に問い合わせず、推測もせず、この `db/schema.py` を Read して確かめる
  (`episode` の題は `title`。推測で書くと `UndefinedColumn` で落ちる)
- NULL を持てる列で並べるときは NULL の向き(降順は `.nulls_last()`)を明示し、`DISTINCT` の結果を順番どおりに使うなら `order_by` を付ける。
  PostGIS の列は `db/postgres/postgis.py`(`.docs/postgres.md`)

## マイグレーション

- マイグレーションは `db/alembic/`。コマンド例は `db/alembic/README` にある。
- `schema.py` を変えたら alembic の `revision --autogenerate` → 内容確認 → `upgrade head` の順(手元の開発用の db に当てる)。
  AWS の db へ当てる決まりは `.claude/docs/aws.md` の決まり 1。列を消す変更は、マージから API の差し替えまでの 1〜2 分だけ古い API が失敗しうる
- 新しいマイグレーションの確かめに、空の db から `upgrade head` で一から上げない(古い版に PostgreSQL で通らないものがあり落ちる)。
  変える前のコミットを `git worktree add --detach <スクラッチパッドの dir> <コミット>` で取り出し、その `db.postgres.init_db --url <テスト用のサーバーの別の db> --create-database`
  で表を作って版を付け、行を足してから、今のブランチで `alembic upgrade head` と `alembic check` を回す。マイグレーションのテスト(上げ下げの往復)は書かない
