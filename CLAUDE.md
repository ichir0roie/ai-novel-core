# 作業指針

## コマンド実行時のエラー対応

コマンド実行でエラーが出たら、直後に握りつぶさず、原因を特定して対策してから作業を再開する。

- 原因がコードにあれば、コードを直す
- 原因が呼び出し方(渡す引数・環境変数・実行手順)にあれば、指示書(この `CLAUDE.md` や各スキルの `SKILL.md` など)を直す

# コーディング規約

コードを読んで内容を理解すること。
コードを読んでも分からない理由のみコメントにする。

## ユーザーの好みを反映するインストラクション

`core`(このリポジトリ)はどの世界でも使い回す汎用の仕組みなので、世界の舞台設定・既存の話から
抽出した文体の癖のような、世界(ユーザー)ごとに違う「好み」は `core` に定数として持たない。

- `core` 側には、システム固有の値(どの世界でも成り立つ既定値。ラノベとしての基本文体など)だけを
  `ai/instructions/` の定数として置く
- ユーザーが追加する値(舞台設定・抽出した文体の癖など)は親リポジトリ(世界リポジトリ)側に
  `core/` と同階層の python モジュール(例: `instructions/style.py`)として置く
- 親リポジトリ側の値は、AI へ渡す文面を組み立てる末端の生成関数(`ai/instructions/style.py` の
  `style_instruction()`、`ai/time_keeper/*_generator.py` の `write` 系、`story_writer.write_next_episode`、
  `claude_code_time_keeper.py` / `local_ai_time_keeper.py` の `claude_*_main` など)の引数として渡す。
  `core` は「引数を渡さなければ空でよい(システム固有の値だけで成り立つ)」設計にする

例: `ai/instructions/style.py` の `shared_extra` / `extra`、`main.py` 以下の `shared_style_extra` /
`style_extra`。呼び出し元(世界リポジトリの `instructions/` や、Claude Code のスキル)がこれらの引数に
自分の値を渡す。

# 文字コード

- リポジトリのテキスト(`.py` `.md` `.json` `.yaml` など)はすべて UTF-8(BOM 無し)。
  ファイルを開くときは必ず `encoding="utf-8"` を付ける
- `novel.db` の文字列も UTF-8(`create_db` が `PRAGMA encoding='UTF-8'` を打つ)。
  `.gitattributes` で `*.db` はバイナリ扱い
- Windows の python は標準出力が cp932 になるため、日本語を出すコマンドは
  `PYTHONUTF8=1` を付けて実行する(付けないと文字化け・`UnicodeEncodeError` になる)

# 環境構築

コード(このリポジトリ `ai-novel-core`)と実データ(`novel.db`)は別リポジトリに分けている。
実データ側のリポジトリ(private の `my-novel-world`)が、このリポジトリをサブモジュール `core/` として持つ。
コードは環境変数 `DEM_WORLD_DIR` で渡されたディレクトリを世界として読み書きする(未設定なら import で止まる)。
python・pytest・alembic は世界リポジトリのルートを cwd にし、`DEM_WORLD_DIR` にそのルートを、
`PYTHONPATH` に `<ルート>/core` を渡して動かす。
`novel.db` の場所は `DEM_NOVEL_DB_PATH` でも差し替えられる。
自分の世界を作るときは、空のリポジトリで `git submodule add https://github.com/ichir0roie/ai-novel-core.git core` する。

git のコマンドは世界リポジトリのルートで打つ。

```
# clone(サブモジュールごと)
git clone --recurse-submodules https://github.com/ichir0roie/my-novel-world.git

# clone 済みで core/ が空のとき
git submodule update --init

# コミットは両方のリポジトリに同じメッセージで。core/ 側を先にコミットしてから世界側で参照を更新する
git -C core switch main   # サブモジュールは detached HEAD になっているため
git -C core add -A
git -C core commit -m "<メッセージ>"
git -C core push
git add -A
git commit -m "<メッセージ>"
git push
```

世界リポジトリの VS Code タスク `git push` は、この順で両方に同じメッセージ(日時)でコミットして push する。

# テスト

- `tests/` に pytest のテストがある。世界リポジトリのルートから `python -m pytest core/tests` で回す。
- テストは `novel.test.db` だけを読み書きする(`tests/conftest.py` が `tool.test` を先に読んで固定する)。
  本番の `novel.db` には触れない
- db・入口・生成器を変えたら、対応するテストを足すか直してから終える
- ただしデータベースのマイグレーション(alembic のリビジョン)にはテストを書かない。
  schema.py とリビジョンの食い違いは `alembic check` を手で打って確かめる
- プルリクを作る前に必ず、変更に対するテストケースを実装し、影響範囲のテストを回し、
  出たエラーを直してから作る

# ユーザがデータを見る・直す窓口

db が唯一の正。ユーザは `gui/` の GUI(FastAPI + Next.js。起動と API は `gui/readme.md`)で `novel.db` を
見て直す。未確認のアイデア・ミームの承認/非承認、星ごとの地図・人物相関図もここで見る。md の写し(`worlds/`)と
その同期(`SyncDb`)は廃止した。Claude は入口越しに db だけで作業を完結させ、報告も db を読んで行う。

`ai/claude_code/interface/` の入口と常駐ループは `/api/interface/{id}` からも呼べる。`claude` コマンドを叩く
入口は Claude Code の環境(`CLAUDECODE=1`)で起こした API でだけ、裏の job として走る(`gui/api/interface.py`)。

`confirmed` は 未確認/承認/非承認 の三段(`db.schema.ConfirmStatus`)で、承認だけが検索・生成・
人物へ引く対象になる。非承認は使わないが、同じ語をまた候補に足さないよう行は残す。

# schema の確認方法

- 列の定義は `db/schema.py` が唯一の正。
- マイグレーションは `db/alembic/`。コマンド例は `db/alembic/README` にある。
- `schema.py` を変えたら alembic の `revision --autogenerate` → 内容確認 → `upgrade head` の順。
