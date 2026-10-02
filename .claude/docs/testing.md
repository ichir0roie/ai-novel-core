# テスト

テストをしてと明確に依頼されたら、そのとき要るテストを `tests/` に書いて実行する(`.venv/bin/python -m pytest tests`)。

## 単体テストと網羅テスト

`CLAUDE.md` の「実装からプルリクまで」の順で回す。

- 単体テスト: 実装の途中に、デバッグのために直している所だけを確かめる(`pytest tests/<file>::<test>`、関数を一つ呼ぶ、画面を一枚撮るなど)。いつ回してもよい
- 網羅テスト: ユーザが実装を認めてから、プルリクの前に一度回す。変えた所に関わるものを全部回し、全部通ってからプルリクを作る
  - python を変えたとき: `.venv/bin/python -m pytest tests`、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python`
  - 画面(`gui/web`)を変えたとき: `gui/web` で `npm run typecheck` と `npm run lint`(`gui/web/node_modules` が無ければ先に `npm ci`。
    web のセッションは入っていないので、無いまま回すと `next` の型が見つからないと落ちる)、テスト用の db で起こした画面での動作確認(`.claude/docs/gui.md`)
  - 落ちたものがあれば直して、網羅テストを回し直す。変えた所と関わりの無い所で落ちるときは、その旨をユーザに伝える

## テストの db

**テスト・デバッグ・動作確認(GUI・API を起こして見る、スクショを撮る、行を足して試す)の db は、手元でも web のセッションでも、
必ず手元の PostGIS のテスト用の db(`novel_test`)にする。本番の RDS(手元の転送 `DEM_DATABASE_URL`・web の API `NOVEL_API_URL`)には
読むだけの確かめでも向けない。** 試しの行を本番に足すと作品の中身に混ざる。

- テストは手元の PostGIS のテスト用の db(`novel_test`。開発用の db と同じサーバー)だけを読み書きする。書くときは
  `tests/conftest.py` で `tool.test` を先に読んで固定する。本番の RDS には書き込まない(`tool.test` は、テスト用の db が
  手元のサーバーを指していなければ止まる)。`DEM_DEV_DATABASE_URL` が無ければ、`tool.test` がその場で `infra_local/postgis.sh` を回して用意する
- テスト用の db は空から作らず、本番の RDS を写して作る(`tool.test.copy_production_db`)。写し元は手元の転送越しの RDS なので、
  転送(`tool.aws.rds --serve`)が要る。手で動きを確かめるときも、これで写した db を使う。
  web のセッション(`CLAUDE_CODE_REMOTE=true`)は RDS に繋がないので写せない(`DEM_DATABASE_URL` が無いと止まる)
- web のセッションでは、PostGIS を `infra_local/postgis.sh` で入れ、空の `novel_test` を schema から作って、要る行を足して使う。
  本番の写しでなければ確かめられないことなら、その旨をユーザに伝え、手元で回すかを尋ねる
  - 用意: `dev=$(bash infra_local/postgis.sh .venv/bin/python) && .venv/bin/python -m db.postgres.init_db --url "${dev%/*}/novel_test" --create-database`
  - 行を足す: `DEM_DEV_DATABASE_URL=$dev .venv/bin/python -m tool.test.seed_mock_db --n 100`(全部の表にモックの行。
    ただし話と人物の結び `episode_character` と作品の親 `parent_story_id` は足さないので、登場人物・章の要る確かめは自分で足す)。
    件数・時期をそろえたいときは、`tool.test` を先に import した使い捨てのスクリプトで `randomizer.mock_factories` に値を渡して足す
  - `conftest.py` の `ensure_test_db` は空の db を写そうとして止まるので、pytest の前に行を足しておく
  - pytest を回すと行が足されるので、確かめに使う id は決め打ちせず、回すたびに引き直す
  - セッションの途中で PostGIS が止まっていることがある(`connection refused`)。`infra_local/postgis.sh` を回し直せば立ち上がり、db の中身は残る
- `conftest.py` はテストの始めに `tool.test.ensure_test_db` を回す。テスト用の db が無いか空のときだけ写し、行があればそのまま使う
  (前のテストで足した行も残る)。作り直すのは `.venv/bin/python -m tool.test.recreate_db`(VS Code はタスク「test db recreate」。
  `seed_mock_db --recreate` も写し直す)。マイグレーションを足したあと、版の食い違いの警告が出たときも作り直す
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、
  `ai.claude_code.ai_client.generate` を差し替える
- alembicのテスト、ダウングレードのテストはやらない。
