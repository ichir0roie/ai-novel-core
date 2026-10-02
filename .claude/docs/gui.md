# GUI

- `gui/` の GUI(API :8765 / 画面 :3000)は、ユーザが db(RDS)を見て直す窓口。起動・停止はユーザが行う(`gui/readme.md` の「起動」)
- Claude が起こすのは、テスト・動作確認で GUI が要るときだけ
- 作業の区切りに GUI が動いているかを確かめたり、落ちたのを立て直したりしない

## 起こす

- ポート(8765 / 3000)・ビルド先(`.next`)をユーザのものと分ける。同じだとユーザの GUI を落とす(`gui.dev` は指定ポートを使う処理を止めてから起こし、`next dev` はビルド先ごとに 1 つしか動かない)
- 起こした API は、渡した `DEM_DATABASE_URL` の db を読み書きする(手元の既定は本番の RDS)。読むだけでも必ずテスト用の db(`novel_test`、`.claude/docs/testing.md`)に向け、`DEM_DATABASE_URL` を省いて起こさない
- `run_in_background` で裏で起こす:
  - API と画面: `dev=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)} && DEM_DATABASE_URL="${dev%/*}/novel_test" DEM_DATABASE_IAM_AUTH=0 NOVEL_WEB_DIST_DIR=.next-test .venv/bin/python -m gui.dev --no-browser --api-port 18765 --web-port 13000`
  - API だけで足りるとき: 同じ環境変数で `.venv/bin/python -m uvicorn gui.api.app:app --port 18765`
- `gui/web` の依存が無ければ `npm ci` で入れる(web のセッションには無い)。`npm ci` が落ちても `npm install` で代えない(`package-lock.json` が書き換わる)
- 前に起こしたものが残っていると `gui.dev` が止まる。`pkill -f '[n]ext dev'` などで止めてから起こす(`pkill` の書き方は `.claude/docs/command-errors.md`)

## 見る・撮る

- 画面は `http://localhost:13000` で開く。`127.0.0.1` だと `next dev` が開発用の資源を別の origin として拒み(`allowedDevOrigins`)、画面が組み上がらない(ページは 200 なのに要素が出ない)。プロキシやログインを疑って回り道しない
- API が 500 を返す・撮影が時間切れになるときは、まず PostGIS が止まっていないかを見る(`.claude/docs/testing.md`)
- 撮るのは Playwright。`.venv` に python の playwright は無い。スクラッチパッドで `npm i playwright-core` し、node のスクリプトで `chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })` から開く
- 撮った画像は `SendUserFile` に `display: "render"` を付けて送る

## 止める

- 使い終わったら止め、18765 / 13000 が閉じたことを確かめる(`curl -s -o /dev/null -w '%{http_code}' <URL>` が `000`。手元は `ss -ltn` でもよい)
- 起こした・ビルドしたあとは `git status` を見て、`tsconfig.json`・`package-lock.json` などが変わっていたら `git checkout` で戻す
