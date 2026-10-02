# テスト

テストをしてと明確に依頼されたら、そのとき要るテストを `tests/` に書いて実行する(`.venv/bin/python -m pytest tests`)。
db は `CLAUDE.md` の「デバッグ・テストの db」のとおり、手元でも web のセッションでもテスト用の db(`novel_test`)だけを使う。
web のセッションでも `novel_test` は手元に作れるので、「本番の db に繋げない」はテストを省く理由にならない。

## 単体テストと網羅テスト

`CLAUDE.md` の「実装からプルリクまで」の順で回す。

- 単体テスト: 実装の途中に、デバッグのために直している所だけを確かめる(`pytest tests/<file>::<test>`、関数を一つ呼ぶ、画面を一枚撮るなど)。いつ回してもよい
- 網羅テスト: ユーザが実装を認めてから、プルリクの前に一度回す。変えた所に関わるものを全部回し、全部通ってからプルリクを作る
  - python を変えたとき: `.venv/bin/python -m pytest tests -q -p no:warnings`、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python`
    (`-p no:warnings` を付けないと、SQLAlchemy の警告に結果の行が埋もれる)
  - 画面(`gui/web`)を変えたとき: `gui/web` で `npm run typecheck` と `npm run lint`(依存が無ければ先に `npm ci`)、テスト用の db で起こした画面での動作確認(`.claude/docs/gui.md`)
  - 落ちたものがあれば直して、網羅テストを回し直す。変えた所と関わりの無い所で落ちるときは、その旨をユーザに伝える

## テスト用の db を用意する

`novel_test` は開発用の db と同じ手元の PostGIS のサーバーに置く。`tests/conftest.py` は `tool.test` を先に読んで db を `novel_test` に固定し
(手元のサーバーを指していなければ止まる)、始めに `tool.test.ensure_test_db` を回す。`ensure_test_db` は db が無いか空のときだけ本番を写し、
行があればそのまま使う(前のテストで足した行も残る)。`DEM_DEV_DATABASE_URL` が無ければ、`tool.test` が `infra_local/postgis.sh` を回して用意する。

- 手元: 本番の RDS を写して作る(`tool.test.copy_production_db`。転送 `tool.aws.rds --serve` が要る)。手で動きを確かめるときも、これで写した db を使う。
  作り直すのは `.venv/bin/python -m tool.test.recreate_db`(VS Code はタスク「test db recreate」)。マイグレーションを足したあと、版の食い違いの警告が出たときも作り直す
- web のセッション: RDS に繋がないので写せない。空の `novel_test` を schema から作り、モックの行を足してから pytest を回す
  (空のままだと `ensure_test_db` が写そうとして止まる)。本番の写しでなければ確かめられないことなら、その旨をユーザに伝え、手元で回すかを尋ねる
  - 用意: `dev=$(bash infra_local/postgis.sh .venv/bin/python) && .venv/bin/python -m db.postgres.init_db --url "${dev%/*}/novel_test" --create-database`。
    `CREATE DATABASE novel_test TEMPLATE novel_dev` で写して作らない(連番が揃わず、行を足すと主キーが重なって落ちる)
  - 行を足す: `DEM_DEV_DATABASE_URL=$dev .venv/bin/python -m tool.test.seed_mock_db --n 100`(全部の表にモックの行)。
    話と人物の結び `episode_character` と作品の親 `parent_story_id` は足さないので、登場人物・章の要る確かめは自分で足す。
    件数・時期をそろえたいときは、`tool.test` を先に import した使い捨てのスクリプトで `randomizer.mock_factories` に値を渡して足す

使うときの注意:

- pytest を回すと行が足されるので、確かめに使う id は決め打ちせず、回すたびに引き直す
- セッションの途中で PostGIS が止まっていることがある(`connection refused`、API の 500)。`infra_local/postgis.sh` を回し直せば立ち上がり、db の中身は残る
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、`ai.claude_code.ai_client.generate` を差し替える

## web の流れ(`web_session/`)を確かめる

- 新しい段・入口を確かめるために、マージやデプロイをして本番の API で試さない(手元に起こした API には今のコードの段がある)
- テスト用の db に向けた API を手元に起こす(`.claude/docs/gui.md`。`NOVEL_API_KEYS` を渡さなければ合言葉を確かめない)。
  流れを回すコマンドには必ず `NOVEL_API_URL=http://127.0.0.1:18765` を付ける。web のセッションの環境には本番の `NOVEL_API_URL` / `NOVEL_API_KEY` が
  入っているので、付け忘れると本番に書く。どの段が呼ばれたかは API のログ(`POST /api/steps/<段の id>`)で確かめる
