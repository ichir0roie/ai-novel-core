# 環境構築

コード(このリポジトリ `ai-novel-core`)と実データ(`novel.db`)は別リポジトリに分けている。
実データ側のリポジトリ(private の `my-novel-world`)が、このリポジトリをサブモジュール `core/` として持つ。
コードは環境変数 `DEM_WORLD_DIR` で渡されたディレクトリを世界として読み書きする(未設定なら import で止まる)。
python・pytest・alembic は世界リポジトリのルートを cwd にし、`DEM_WORLD_DIR` にそのルートを、
`PYTHONPATH` に `<ルート>/core` を渡して動かす。
`novel.db` の場所は `DEM_NOVEL_DB_PATH` でも差し替えられる。
自分の世界を作るときは、空のリポジトリで `git submodule add https://github.com/ichir0roie/ai-novel-core.git core` する。

git のコマンドは世界リポジトリのルートで打つ。

世界リポジトリの VS Code タスク `git push` は、この順で両方に同じメッセージ(日時)でコミットして push する。
