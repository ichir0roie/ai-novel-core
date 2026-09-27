# 作業指針

## ローカル環境
コード修正であっても常に現在のブランチ(主に main)上で直接作業する。


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

# 「更新」の依頼があった場合
- main ブランチへのコミットを頼まれたときは、深く調査しない
- 変更内容を掘り下げて「なぜ」まで書いた丁寧なメッセージを作らず、diff・変更ファイルの表層だけを見て、端的なメッセージでそのままコミットする
- プッシュ前に、最新の変更を取り込んで、コンフリクトがあれば解消してからpush
- コミットは `core/`(このリポジトリ)と世界リポジトリ(my-novel-world)の両方に同じメッセージで行う。
  手順は「環境構築」のとおり `core/` → 世界の順

# 文字コード

- リポジトリのテキスト(`.py` `.md` `.json` `.yaml` など)はすべて UTF-8(BOM 無し)。
  ファイルを開くときは必ず `encoding="utf-8"` を付ける
- `novel.db` の文字列も UTF-8(`create_db` が `PRAGMA encoding='UTF-8'` を打つ)。
  `.gitattributes` で `*.db` はバイナリ扱い
- Windows の python は標準出力が cp932 になるため、日本語を出すコマンドは
  `PYTHONUTF8=1` を付けて実行する(付けないと文字化け・`UnicodeEncodeError` になる)

# 環境構築

コード(このリポジトリ `ai-novel-core`)と実データ(`novel.db`・`worlds/`)は別リポジトリに分けている。
実データ側のリポジトリ(private の `my-novel-world`)が、このリポジトリをサブモジュール `core/` として持つ。
コードは環境変数 `DEM_WORLD_DIR` で渡されたディレクトリを世界として読み書きする(未設定なら import で止まる)。
python・pytest・alembic は世界リポジトリのルートを cwd にし、`DEM_WORLD_DIR` にそのルートを、
`PYTHONPATH` に `<ルート>/core` を渡して動かす。
md と db の同期(`SyncDb`)が使う `novel.db` と `worlds/` は、それぞれ `DEM_NOVEL_DB_PATH` / `DEM_WORLDS_DIR` でも個別に差し替えられる。
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

# db への接続

- コードから触るときは `from db.schema import get_env_session` で `Session` を開く。
  `engine` も同じモジュールにある
- 作業として db を読み書きするときは `ai/claude_code/interface/` の入口越しに、
  既存の python コードを呼んで行う。
- `ai/claude_code/interface/readme.md` を操作前のマニュアルとする。
  操作の前にその「依頼内容 → 呼ぶコード」の対応表を引き、依頼に当たる入口を呼ぶ
- 対応する入口が無ければ、readme の「作り方」に沿って入口を新しく作ってから行う。
  足したら同じ作業のうちに readme の対応表へ行を足す(表に無い入口は次から見えない)
- 読み取り(`select`)だけなら入口を通さなくてよい。python の `sqlite3` や SQLAlchemy で
  好きに覗いてよい。読むだけなら同期(`SyncDb`)も回さなくてよい。
  書き込み(`insert` `update` `delete`)は必ず入口越しに行う
- 調査用の読み取り例(世界リポジトリのルートで `.venv/bin/python` を使う。`core/` は `.venv` の場所を持たない):

```
.venv/bin/python -c "
import sqlite3
from db.schema import NOVEL_DB_PATH
c = sqlite3.connect(NOVEL_DB_PATH)
print(c.execute('select count(*) from character').fetchone())
"
```

# md と db の同期

db が正で、`worlds/` の md はユーザが db を読み書きするための窓口。Claude は db だけで作業を完結させ、
md を読んで判断したり、md を直接書き換えたりはしない(`worlds/**/*.md` は直接変更しない)。

同期は入口 `sync.sync_db.SyncDb()`(`tool.markdown.sync_db`)で行う。差分だけを動かすので、いつ何度呼んでもよい。

- `worlds/` の隣の `.markdown_sync.json`(台帳)に、md ごとに前回の同期時点の md と db の中身のハッシュを持つ
- 取り込み(`import_db`)は、台帳と中身が違う md(ユーザが手で直した・足した md)だけを db へ入れる。
  台帳が無ければすべての md を取り込む
- 台帳に載っているのに無くなった md(ユーザが手で消した md)は、同じ行を持つ md が他に無ければ db からも行を消す
- 書き出し(`export_db`)は、db と中身が違う md だけを書き直し、db に行が無くなった md を消す。
  手で直された md が残っていれば止まる(`force=True` で md を捨てて押し切る)
- `sync_db` は取り込み → 書き出しの順に回す。同じ行を md と db の両方で直していたら、
  md(ユーザの直接編集)を勝たせ、`conflicts` に返す。返ってきたら db 側でした修正をやり直す
- 同期は `worlds/` の隣の `.markdown_sync.lock` で、セッションをまたいで一度に一つだけ走る

db を修正する作業は、入口越しの修正 → `SyncDb()` の順で回す(ローカルでもクラウドでも同じ)。
ユーザが md を直していそうなら、作業の前にも `SyncDb()` を回して取り込んでおく。


# schema の確認方法

- 列の定義は `db/schema.py` が唯一の正。

- マイグレーションは `db/alembic/`。コマンド例は `db/alembic/README` にある。
- `schema.py` を変えたら alembic の `revision --autogenerate` → 内容確認 → `upgrade head` の順。
