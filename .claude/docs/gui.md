# GUI

`gui/` の GUI(API :8765 / 画面 :3000)は、ユーザが db(RDS)を見て直す窓口。起動・停止はユーザが任意で行う
(`gui/readme.md` の「起動」)。Claude は、テスト・動作確認で GUI が要るときだけ起こす。
作業の区切りに GUI が動いているかを確かめたり、落ちているのを立て直したりはしない。

- テストで起こすサーバーは、ユーザの使うポート(8765 / 3000)と別のポートにする。`gui.dev` は指定したポートを
  使っている処理を止めてから起こすので、同じポートだとユーザの GUI を落とす
- 画面を起こすときは、ビルド先も `.next-test` に分ける(`NOVEL_WEB_DIST_DIR`)。`next dev` はビルド先ごとに 1 つしか
  動かせず、同じビルド先だとユーザの `gui.dev` と片方が起動に失敗する
  - API と画面: `NOVEL_WEB_DIST_DIR=.next-test .venv/bin/python -m gui.dev --no-browser --api-port 18765 --web-port 13000`
  - API だけで足りるとき: `.venv/bin/python -m uvicorn gui.api.app:app --port 18765`
- 裏で起こし(`run_in_background`)、使い終わったら `kill -TERM` で止め、18765 / 13000 が閉じたことを確かめる
  (手元は `ss -ltn`。web のセッションには `ss` が無いので、下の `curl` で `000` が返るかを見る)
- 起こした API は、渡した `DEM_DATABASE_URL` の db を読み書きする(手元の既定は本番の RDS)。**テスト・動作確認で起こすときは、
  読むだけでも、手元でも web のセッションでも、必ず手元の PostGIS のテスト用の db(`novel_test`、`.claude/docs/testing.md`)に向ける。**
  `DEM_DATABASE_URL` を省いて起こさない:
  - API: `dev=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)} && DEM_DATABASE_URL="${dev%/*}/novel_test" DEM_DATABASE_IAM_AUTH=0 .venv/bin/python -m uvicorn gui.api.app:app --port 18765`
  - API と画面: 同じ `DEM_DATABASE_URL` / `DEM_DATABASE_IAM_AUTH=0` を付けて上の `gui.dev` を起こす
- web のセッションには `ss` が無い。`gui.dev` はポートを空けられずに止まるので、前に起こしたものは `pkill -f '[n]ext dev'` などで止めてから起こす
- `pkill -f` のパターンは、必ず一字を `[]` で囲む(`pkill -f '[u]vicorn gui.api.app'`)。囲まないと、そのコマンドを回しているシェル自身にも
  当たってシェルごと止まる(exit 144)。止まったかは `curl -s -o /dev/null -w '%{http_code}' <URL>` が `000` を返すかで確かめる
- `gui/web` の依存は `npm ci` で入れ、`npm ci` が落ちても `npm install` で代えない(`package-lock.json` が書き換わる)。
  画面を起こした・ビルドしたあとは `git status` を見て、`tsconfig.json`・`package-lock.json` などが変わっていたら `git checkout` で戻す
- 画面は `http://localhost:13000` で開く。`127.0.0.1` で開くと `next dev` が開発用の資源を別の origin として拒み(`allowedDevOrigins`)、
  画面が組み上がらない(ページは 200 を返すのに、`.timeline-item` などの要素がいつまでも出ない)。プロキシやログインを疑って回り道しない
- API が `/api/tables` などで 500 を返す・撮影が時間切れになるときは、まず PostGIS が止まっていないかを見る
  (`infra_local/postgis.sh` を回し直す。`.claude/docs/testing.md`)
- 撮った画像は `SendUserFile` に `display: "render"` を付けて送り、その場で見えるようにする
- 画面を撮るときは Playwright(`executablePath: '/opt/pw-browsers/chromium'`)で開き、撮った画像は `SendUserFile` でユーザに見せられる。
  `.venv` に python の playwright は無いので、スクラッチパッドで `npm i playwright-core` し、node のスクリプトで
  `chromium.launch({ executablePath: '/opt/pw-browsers/chromium' })` から開く
