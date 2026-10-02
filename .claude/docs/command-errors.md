# コマンド実行時のエラー対応

コマンド実行でエラーが出たら、直後に握りつぶさず、原因を特定して対策してから作業を再開する。

- 原因がコードにあれば、コードを直す
- 原因が呼び出し方(渡す引数・環境変数・実行手順)にあれば、指示書(`CLAUDE.md`・`.claude/docs/` のドキュメント・各スキルの `SKILL.md` など)を直す

## これまでにつまずいた所

場面ごとのものは各文書にある(画面は `gui.md`、テスト用の db・PostGIS の停止は `testing.md`、web の API は `web-db.md`、`.venv`・uv は `setup.md`)。
どの場面でも起きるものをここに置く。

- exit 144 でシェルごと止まった: `pkill -f` / `pgrep -f` のパターンが自分のシェルにも当たった。一字を `[]` で囲む(`'[n]ext dev'`)
- 使い捨てのスクリプトで import が落ちた: スクラッチパッドのファイル名が標準ライブラリを隠した(`inspect.py` など)。`check_<対象>.py` のように名付ける
- 一括置換が当たらないまま進んだ: python の `str.replace` は当たらなくても黙る。`assert t.count(old) == 1` を付けて、当たらなければ止める
- auto mode の判定が返らず(no verdict)ツールが止まった: 一時的なもの。少し置いて同じ呼び出しをやり直す
- 裏で回しているコマンドを止めたい: `pkill` ではなく、そのタスクの id で `TaskStop` する。残りが無いかは `pgrep -af '[g]enerate_episode'` などで見る
- `npm ci`・`pip`・`curl` がプロキシで落ちた(`proxy`・`403`・TLS): `/root/.ccr/README.md` と `curl -sS "$HTTPS_PROXY/__agentproxy/status"` を見て、
  道具ごとの直し方でやり直す。それでも通らなければユーザに伝えて止まる。落ちたチェック(typecheck・lint など)を飛ばして先へ進まない
- AWS の MCP が `expired or invalid AWS credentials` で落ちた: 打ち直しても直らない。ユーザに伝え、実データを見ずに答えるならそのことを明記する
