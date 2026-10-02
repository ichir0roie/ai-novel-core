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
- 裏で起こし(`run_in_background`)、使い終わったら `kill -TERM` で止め、18765 / 13000 が閉じたことを `ss -ltn` で確かめる
- 起こした API は、渡した `DEM_DATABASE_URL` の db を読み書きする(手元の既定は本番の RDS)。**テスト・動作確認で起こすときは、
  読むだけでも、手元でも web のセッションでも、必ず手元の PostGIS のテスト用の db(`novel_test`、`.claude/docs/testing.md`)に向ける。**
  `DEM_DATABASE_URL` を省いて起こさない:
  - API: `dev=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)} && DEM_DATABASE_URL="${dev%/*}/novel_test" DEM_DATABASE_IAM_AUTH=0 .venv/bin/python -m uvicorn gui.api.app:app --port 18765`
  - API と画面: 同じ `DEM_DATABASE_URL` / `DEM_DATABASE_IAM_AUTH=0` を付けて上の `gui.dev` を起こす
- web のセッションには `ss` が無い。`gui.dev` はポートを空けられずに止まるので、前に起こしたものは `pkill -f '[n]ext dev'` などで止めてから起こす
- 画面を撮るときは Playwright(`executablePath: '/opt/pw-browsers/chromium'`)で開き、撮った画像は `SendUserFile` でユーザに見せられる
