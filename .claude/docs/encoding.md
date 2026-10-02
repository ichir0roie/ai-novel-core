# 文字コード

- リポジトリのテキスト(`.py` `.md` `.json` `.yaml` など)はすべて UTF-8(BOM 無し)
- ファイルを開くときは必ず `encoding="utf-8"` を付ける
- db(PostgreSQL)も UTF-8 で作る(`db.postgres.init_db` の `CREATE DATABASE ... ENCODING 'UTF8'`)
- 日本語を出すコマンドは `PYTHONUTF8=1` を付けて実行する(Windows の python は標準出力が cp932 になり、付けないと文字化け・`UnicodeEncodeError` になる)
