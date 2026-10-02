# web のセッションでの db(`CLAUDE_CODE_REMOTE=true`)

Claude Code on the web のセッションは db(RDS)に繋がない。db の読み書きは、画面(Amplify)の `/api/*` を
web 用の合言葉付きで叩いて、Lambda の API に頼む(理由と環境の設定は `.docs/web-session.md`)。
手元の db の決まり(`.claude/docs/db.md`)は、この場では読まない。

## 決まり

- db に直に繋ごうとしない。`DEM_DATABASE_URL` を組まない、`tool.aws.rds` を使わない、踏み台やトンネルを試さない
- **テスト・デバッグ・動作確認では、この API(本番の RDS)を使わない。** 必ず手元の PostGIS のテスト用の db(`novel_test`)を
  用意して使う(`.claude/docs/testing.md`)。ここの決まりは作業として db を読み書きするときのもの
- 何を呼ぶかは、手元と同じく `data_access_logic/readme.md` の「依頼内容 → 呼ぶコード」の表で引く。呼び方だけが下のように変わる
- API に口の無い作業は、web の中で回り道を作らず、「手元で行うか、口を足すコードの変更が要る」とユーザに伝える
- マイグレーションは当てない(`.claude/docs/aws.md` の決まり 1)
- 合言葉(`NOVEL_API_KEY`)は環境変数のまま渡し、値・URL を報告やログに出さない

## 呼び方

`curl` は `.venv` の用意を待たずに打てる。コマンドの頭で `api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"` を置く。

| したいこと | 呼び方 |
| --- | --- |
| id を名前から引く | `curl -sS -G -H "$h" "$api/api/tables/<表>/options" --data-urlencode 'q=<名>'`(`q` は本文にも当たる) |
| 行を並べる・絞る | `curl -sS -H "$h" "$api/api/tables/<表>/records?<列>=<値>&sort=<列>&order=asc&limit=500"` |
| 行を一つ読む | `curl -sS -H "$h" "$api/api/tables/<表>/records/<id>"`(`.record` に列が入る) |
| db だけの入口(claude を叩かない) | `curl -sS -H "$h" -H 'content-type: application/json' -d '{"args":{...}}' "$api/api/interface/<入口の id>"` |
| claude を叩く入口 | web の流れを python で回す(`web_session/flows.py` の対応表。入口と同じ引数)。下の例 |

claude を叩く入口の web の流れは、AI(`claude -p`)をこのセッションで回し、db の段だけを API で呼ぶ。数分〜十数分かかるので
`run_in_background` で回す。入口の id と引数(JSON の形)で回すなら:

```
.venv/bin/python -c "
import json
from data_access_logic.logs import configure_logging
from web_session.flows import run
configure_logging()
print(json.dumps(run('<入口の id>', {<引数>}), ensure_ascii=False))
"
```

API に届かないときは `.venv/bin/python -m web_session.check_api` を回し、出力と `.docs/web-session.md` の「確かめる」の表を見る。

## 画面から積まれた AI の依頼

画面(web)の AI のボタンは待ち行列(`ai_task`)に積むだけ。回すのはユーザに頼まれたとき(スキル `run-ai-tasks`)。
