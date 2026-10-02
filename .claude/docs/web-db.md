# web のセッションでの db(`CLAUDE_CODE_REMOTE=true`)

- web のセッションは db(RDS)に繋がない。画面(Amplify)の `/api/*` を web 用の合言葉付きで叩き、Lambda の API に読み書きを頼む(理由と環境の設定は `.docs/web-session.md`)
- 手元の db の決まり(`.claude/docs/db.md`)は、ここでは読まない

## 決まり

- db に直に繋ごうとしない。`DEM_DATABASE_URL` を組まない、`tool.aws.rds` を使わない、踏み台やトンネルを試さない
- プロキシ越しに任意のホスト・ポート(5432 など)へ繋がるかも試さない(VM は HTTPS のプロキシしか通さず、auto mode に止められる)
- 始める前に `NOVEL_API_URL` / `NOVEL_API_KEY` が環境にあるかを確かめる(値は出さず、空かどうかだけ見る)
- 空なら専用でない環境で開いている。作業を止め、`.docs/web-session.md` の環境の作り方をユーザに案内する
- 合言葉をチャットに貼ってもらわない(貼られたら作り直しを案内する)
- この API は作業として db を読み書きするときだけ使う。テスト・デバッグ・動作確認では使わない(`CLAUDE.md` の「デバッグ・テストの db」)
- 何を呼ぶかは、手元と同じく `data_access_logic/readme.md` の「依頼内容 → 呼ぶコード」の表で引く。呼び方だけが下のように変わる
- API に口の無い作業は、web の中で回り道を作らず、「手元で行うか、口を足すコードの変更が要る」とユーザに伝える
- マイグレーションは当てない(`.claude/docs/aws.md` の決まり 1)
- 合言葉(`NOVEL_API_KEY`)は環境変数のまま渡し、値・URL を報告やログに出さない

## 呼び方

- `curl` は `.venv` の用意を待たずに打てる
- コマンドの頭に `api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"` を置く(末尾の `/` を落とさないと 308 が返り、`jq` が `Invalid numeric literal` で落ちる)
- 応答の JSON は、一覧が `.items`、一件が `.record`、入口の呼び出しが `.result` に入る
- 入口の返す見出しは入口ごとに違う(`ReadEpisodeCasting` / `ReadEpisodeBrief` は日本語、`ReadEpisodeTexts` は列名の英語)。決めつけて整形せず、先に一件を見て確かめる
- 日本語の見出しを `jq` で引くときは `.["話id"]` のように引用する
- 状態コードを見たいときは、本文を `-o <ファイル>` に書き出し、`-w '%{http_code}'` を本文と分ける(混ぜると JSON が読めない)

| したいこと | 呼び方 |
| --- | --- |
| id を名前から引く | `curl -sS -G -H "$h" "$api/api/tables/<表>/options" --data-urlencode 'q=<名>'`(`q` は本文にも当たる) |
| 行を並べる・絞る | `curl -sS -H "$h" "$api/api/tables/<表>/records?<列>=<値>&sort=<列>&order=asc&limit=500"` |
| 行を一つ読む | `curl -sS -H "$h" "$api/api/tables/<表>/records/<id>"`(`.record` に列が入る) |
| db だけの入口(claude を叩かない) | `curl -sS -H "$h" -H 'content-type: application/json' -d '{"args":{...}}' "$api/api/interface/<入口の id>"` |
| claude を叩く入口 | web の流れを python で回す(`web_session/flows.py` の対応表。入口と同じ引数)。下の例 |

claude を叩く入口の web の流れは、AI(`claude -p`)をこのセッションで回し、db の段だけを API で呼ぶ。数分〜十数分かかるので `run_in_background` で回す。入口の id と引数(JSON の形)で回す例:

```
.venv/bin/python -c "
import json
from data_access_logic.logs import configure_logging
from web_session.flows import run
configure_logging()
print(json.dumps(run('<入口の id>', {<引数>}), ensure_ascii=False, indent=2))
"
```

- id と引数は、スキルや `data_access_logic/readme.md` の表のもの(手元と同じ)
- 長い出力は `> <scratchpad>/<名>.json` へ書き出して Read する
- 本文・プロットのような長い文字列は、スクラッチパッドのファイルに置き、引数の中で `Path('<scratchpad>/<名>.txt').read_text(encoding='utf-8')` と読む(`from pathlib import Path` を足す)

API に届かない(`ApiError`)・版が食い違う・段が無いと返るとき:

- `.venv/bin/python -m web_session.check_api` を回し、出力と `.docs/web-session.md` の「確かめる」の表を見る
- `ProxyError: 403`(プロキシが CONNECT を断った)なら、環境の Network access に API のホストが入っていない。`curl -sS "$HTTPS_PROXY/__agentproxy/status"` の失敗の記録で断られたホストを確かめ、許可先に足すようユーザに頼んで止まる(コードでは直せない)

