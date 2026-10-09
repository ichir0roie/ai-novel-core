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
- curl の応答の JSON は、一覧が `.items`、一件が `.record`、入口の呼び出しが `.result` に入る。`flows.run` の返りは `.result` に包まれず、入口の結果がそのまま返る
- 入口の返す見出しは入口ごとに違う(`ReadEpisodeCasting` / `ReadEpisodeBrief` は日本語、`ReadEpisodeTexts` は列名の英語)。決めつけて整形せず、先に `jq 'keys'` で見出しを見て確かめる(話の入口の見出しはスキル `episode` の「入口の返す形」)
- `jq` の書き方は `.claude/docs/setup.md` の「jq」(日本語の見出しの引用・無い鍵が黙って null になること)
- 状態コードを見たいときは、本文を `-o <ファイル>` に書き出し、`-w '%{http_code}'` を本文と分ける(混ぜると JSON が読めない)

| したいこと | 呼び方 |
| --- | --- |
| id を名前から引く | `curl -sS -G -H "$h" "$api/api/tables/<表>/options" --data-urlencode 'q=<名>'`(`q` は本文にも当たる) |
| 行を並べる・絞る | `curl -sS -H "$h" "$api/api/tables/<表>/records?<列>=<値>&sort=<列>&order=asc&limit=500"` |
| 行を一つ読む | `curl -sS -H "$h" "$api/api/tables/<表>/records/<id>"`(`.record` に列が入る) |
| db だけの入口(claude を叩かない) | `curl -sS -H "$h" -H 'content-type: application/json' -d '{"args":{...}}' "$api/api/interface/<入口の id>"`(結果は `.result`) |
| claude を叩く入口 | `web_session/flows.py` の `run` で、入口の id と引数(手元と同じ)を渡して python で回す。下の例(結果は包まれずにそのまま返る) |

- どちらで呼ぶかは、`curl -sS -H "$h" "$api/api/interface" | jq -r '.entrances[].id'` の一覧で見る。一覧にあるのが db だけの入口で、無いもの(`ReadEpisodeCasting`・`ReadEpisodeBrief`・`CommitEpisode`・`GenerateCharacter`・`CommitEvent` など)は `flows.run` で回す
- claude を叩く入口を curl で呼ぶと、`{"detail":"… は claude コマンドを叩くので API からは呼べない …"}` が返る。打ち直さずに `flows.run` に替える

## 表の API(`/api/tables`)

- 表の API で読めるのは `story`・`episode`・`character`・`character_relation`・`event`・`location`・`idea`・`meme`・`oracle`・`style_preference` だけ。ほかの表(`episode_character`・`character_location`・`episode_character_session` など)は `{"detail":"GUI で扱わないテーブル: …"}` が返る。消す口(DELETE)も無い。代わりに次を使う:

| 読みたいもの | 読み方 |
| --- | --- |
| 話の登場人物・名前だけ出る人物 | `episode` の行の `character_ids` / `mentioned_character_ids` |
| 人物の居場所 | 入口 `character.read_character.ReadCharacter` の `locations` |
| 話のセッションの行(読む・消す) | `.venv/bin/python -m tool.episode_session read --episode <id>` / `clear --episode <id>`(`--from <行の id>` でその行から後だけ) |
| 話の概要(`summary_text`) | 入口 `episode.read_episode_texts.ReadEpisodeTexts` `{"episode_ids":[…]}` の `.result[].summary_text`(表の API の行には入らない) |

- 列名は推測しない。`curl -sS -H "$h" "$api/api/tables" | jq -c '.tables[] | {name, columns: [.columns[].key]}'` で表ごとの列を見る。取り違えやすいもの:

| 表 | 正しい列 | 取り違えた名前 |
| --- | --- | --- |
| `story` | `name`・`parent_story_id` | `title`・`parent_id` |
| `idea` | `parent_idea_id` | `parent_id` |
| `character_relation` | `character_1_id`・`character_2_id` | `from_character_id`・`to_character_id`・`character_id` |
| `episode` | (概要は表の API に無い。上の表) | `summary`・`summary_text` |

- 一覧(`/records?…`)の項目には本文の列(`text`、`episode` は `plot_text`・`main_text`、`character` は `appearance`・`meme`・`principle`・`plot` も)が入らず、代わりに `label` と本文の頭の `preview` が入る。話に本文があるかは `letters`(字数)で見る。本文そのものは一件(`/records/<id>` の `.record.main_text`)か `ReadEpisodeTexts` で読む

claude を叩く入口は、手元と同じ流れ(`data_access_logic/flows/`)で AI(`claude -p`)をこのセッションで回し、db の段だけを API で呼ぶ。数分〜十数分かかるので `run_in_background` で回す。入口の id と引数(JSON の形)で回す例:

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

API に届かない(`ApiError`)・バージョンが食い違う・段が無いと返るとき:

- `.venv/bin/python -m web_session.check_api` を回し、出力と `.docs/web-session.md` の「確かめる」の表を見る
- `ProxyError: 403`(プロキシが CONNECT を断った)なら、環境の Network access に API のホストが入っていない。`curl -sS "$HTTPS_PROXY/__agentproxy/status"` の失敗の記録で断られたホストを確かめ、許可先に足すようユーザに頼んで止まる(コードでは直せない)

