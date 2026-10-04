# テスト

- テストをしてと明確に依頼されたら、要るテストを `tests/` に書いて回す(`.venv/bin/python -m pytest tests`)
- db は手元でも web のセッションでもテスト用の db(`novel_test`)だけを使う(`CLAUDE.md` の「デバッグ・テストの db」)
- web のセッションでも `novel_test` は手元に作れる。「本番の db に繋げない」はテストを省く理由にならない

## 単体テストと網羅テスト

`CLAUDE.md` の「実装からプルリクまで」の順で回す。

- 単体テスト: 実装の途中、デバッグのために直している所だけを確かめる(`pytest tests/<file>::<test>`、関数を一つ呼ぶ、画面を一枚撮るなど)。いつ回してもよい
- 網羅テスト: ユーザが実装を認めてから、プルリクの前に一度回す。変えた所に関わるものを全部回し、全部通ってからプルリクを作る
  - python を変えたとき: `.venv/bin/python -m pytest tests -q -p no:warnings`(`-p no:warnings` が無いと SQLAlchemy の警告に結果が埋もれる)、ルートで `uvx ruff check .` と `npx pyright --pythonpath .venv/bin/python`
  - 画面(`gui/web`)を変えたとき: `gui/web` で `npm run typecheck` と `npm run lint`(依存が無ければ先に `npm ci`)、テスト用の db で起こした画面での動作確認(下の「GUI を起こす」)
  - 落ちたら直して、網羅テストを回し直す。変えた所と関わりの無い所で落ちたら、ユーザに伝える

## テスト用の db を用意する

- `novel_test` は開発用の db と同じ手元の PostGIS のサーバーに置く
- `tests/conftest.py` は `tool.test` を先に読んで db を `novel_test` に固定し(手元のサーバーを指していなければ止まる)、始めに `tool.test.ensure_test_db` を回す
- `ensure_test_db` は db が無いか空のときだけ本番を写す。行があればそのまま使う(前のテストで足した行も残る)
- `DEM_DEV_DATABASE_URL` が無ければ、`tool.test` が `infra_local/postgis.sh` を回して用意する
- 手元:
  - 本番の RDS を写して作る(`tool.test.copy_production_db`。転送 `tool.aws.rds --serve` が要る)。手で動きを確かめるときもこの db を使う
  - 作り直しは `.venv/bin/python -m tool.test.recreate_db`(VS Code はタスク「test db recreate」)。マイグレーションを足したあと・バージョンの食い違いの警告が出たときも作り直す
- web のセッション:
  - RDS に繋がないので写せない。空の `novel_test` を schema から作り、モックの行を足してから pytest を回す(空のままだと `ensure_test_db` が写そうとして止まる)
  - 本番の写しでなければ確かめられないことは、ユーザに伝え、手元で回すかを尋ねる
  - 用意: `dev=$(bash infra_local/postgis.sh .venv/bin/python) && .venv/bin/python -m db.postgres.init_db --url "${dev%/*}/novel_test" --create-database`
  - `CREATE DATABASE novel_test TEMPLATE novel_dev` で写して作らない(連番が揃わず、行を足すと主キーが重なって落ちる)
  - 行を足す: `DEM_DEV_DATABASE_URL=$dev .venv/bin/python -m tool.test.seed_mock_db --n 100`(全部の表にモックの行)
  - 話と人物の結び `episode_character` と作品の親 `parent_story_id` は足されない。登場人物・章の要る確かめでは自分で足す
  - 件数・時期をそろえたいときは、`tool.test` を先に import した使い捨てのスクリプトで `randomizer.mock_factories` に値を渡して足す

使い捨てのスクリプトで `novel_test` を読み書きするとき:

- 一行目で `import tool.test` を読む(`db.schema` より先。`db.schema` は import した時に db を固定するので、先に読まれると `db.schema がテスト用の db 以外で先に読み込まれている` で止まる)。pytest のプラグインも同じ
- 向け先は `DEM_DEV_DATABASE_URL=$dev` で渡す(`tool.test` がそこから `novel_test` を組む)。`DEM_DATABASE_URL` に `novel_test` の URL を入れない(`テスト用の db が手元の PostGIS を指していない` で止まる)
- 行は `randomizer.mock_factories` か `seed_mock_db` で足す。手で `insert` や ORM の行を組むと、既定値の無い NOT NULL の列(`idea.meme_seeded`・`episode.letters`・`story.narration` など)で落ちる
- ORM の関連は `lazy="noload"` のものが多く、`s.get_one(Episode, id).characters` は空になる。入口と同じ読み方(`data_access_logic.episode.material.load_episode(s, id)` など)で読む
- AI の差し替え: 引数 `ai` を持つ入口・関数にだけ `MockAIClient()` を渡す。持たない入口(`CommitIdea` など)は `mock.patch("ai.claude_code.ai_client.generate", MockAIClient().generate)` の中で呼ぶ

使うときの注意:

- pytest を回すと行が足される。確かめに使う id は決め打ちせず、回すたびに引き直す
- 前に回した行が溜まると、件数・`limit` に頼るテストが落ちる。マイグレーション・表の定義を変えたあとも、`init_db` は表のある db には作らずに止まり(`表が既にある…`)、古い表のまま回すと列が足りずに落ちる。どちらも `novel_test` を作り直す。手元は `tool.test.recreate_db`、web のセッションは消してから「用意」と「行を足す」を回し直す:

```
dev=$(bash infra_local/postgis.sh .venv/bin/python) && .venv/bin/python -c "
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
admin = create_engine(make_url(sys.argv[1]).set(database='postgres'), isolation_level='AUTOCOMMIT')
with admin.connect() as c:
    c.execute(text('DROP DATABASE IF EXISTS novel_test WITH (FORCE)'))
" "$dev"
```
- セッションの途中で PostGIS が止まることがある(`connection refused`、API の 500)。`infra_local/postgis.sh` を回し直せば立ち上がり、db の中身は残る
- AI を呼ぶ処理では本物の claude を呼ばない。`tool.test.mock_ai_client.MockAIClient` を `ai` に渡すか、`ai.claude_code.ai_client.generate` を差し替える

## web の口(`web_session/`)を確かめる

流れは手元の入口と同じ(`data_access_logic/flows/`)なので、ふだんは pytest で足りる。API 越しの口まで確かめるときだけ、次のようにする。


- 新しい段・入口を確かめるのに、マージやデプロイをして本番の API で試さない(手元に起こした API に今のコードの段がある)
- テスト用の db に向けた API を手元に起こす(下の「GUI を起こす」)。`NOVEL_API_KEYS` を渡さなければ合言葉を確かめない
- 流れを回すコマンドには必ず `NOVEL_API_URL=http://127.0.0.1:18765` を付ける。web のセッションの環境には本番の `NOVEL_API_URL` / `NOVEL_API_KEY` が入っているので、付け忘れると本番に書く
- どの段が呼ばれたかは API のログ(`POST /api/steps/<段の id>`)で確かめる

## GUI を起こす

- `gui/` の GUI(API :8765 / 画面 :3000)は、ユーザが db(RDS)を見て直す窓口。起動・停止はユーザが行う(`gui/readme.md` の「起動」)
- Claude が起こすのは、テスト・動作確認で GUI が要るときだけ
- 作業の区切りに GUI が動いているかを確かめたり、落ちたのを立て直したりしない

### 起こす

- ポート(8765 / 3000)・ビルド先(`.next`)をユーザのものと分ける。同じだとユーザの GUI を落とす(`gui.dev` は指定ポートを使う処理を止めてから起こし、`next dev` はビルド先ごとに 1 つしか動かない)
- 起こした API は、渡した `DEM_DATABASE_URL` の db を読み書きする(手元の既定は本番の RDS)。読むだけでも必ずテスト用の db(`novel_test`)に向け、`DEM_DATABASE_URL` を省いて起こさない
- `run_in_background` で裏で起こす:
  - API と画面: `dev=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)} && DEM_DATABASE_URL="${dev%/*}/novel_test" DEM_DATABASE_IAM_AUTH=0 NOVEL_WEB_DIST_DIR=.next-test .venv/bin/python -m gui.dev --no-browser --api-port 18765 --web-port 13000`
  - API だけで足りるとき: 同じ環境変数で `.venv/bin/python -m uvicorn gui.api.app:app --port 18765`
- `gui/web` の依存が無ければ `npm ci` で入れる(web のセッションには無い)。`npm ci` が落ちても `npm install` で代えない(`package-lock.json` が書き換わる)
- 前に起こしたものが残っていると `gui.dev` が止まる。`pkill -f '[n]ext dev'` などで止めてから起こす(`pkill` の書き方は `.claude/docs/setup.md` の「コマンドのエラー」)

### 見る・撮る

- 画面は `http://localhost:13000` で開く。`127.0.0.1` だと `next dev` が開発用の資源を別の origin として拒み(`allowedDevOrigins`)、画面が組み上がらない(ページは 200 なのに要素が出ない)。プロキシやログインを疑って回り道しない
- API が 500 を返す・撮影が時間切れになるときは、まず PostGIS が止まっていないかを見る(上の「使うときの注意」)
- 撮るのは Playwright。`.venv` に python の playwright は無い。スクラッチパッドで `npm i playwright-core` し、node のスクリプトで `chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })` から開く
- 撮った画像は `SendUserFile` に `display: "render"` を付けて送る

### 止める

- 使い終わったら止め、18765 / 13000 が閉じたことを確かめる(`curl -s -o /dev/null -w '%{http_code}' <URL>` が `000`。手元は `ss -ltn` でもよい)
- 起こした・ビルドしたあとは `git status` を見て、`tsconfig.json`・`package-lock.json` などが変わっていたら `git checkout` で戻す
