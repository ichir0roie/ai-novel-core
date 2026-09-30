# web のセッションでの回し方(`CLAUDE_CODE_REMOTE=true`)

db には繋がない。読むのは API の `curl`、書き直しは入口と同じ処理の web の流れ(`web_session.episode.revise_episode`)で、
AI(`claude -p`)はこのセッションで回し、db の読み書きだけを API に頼む。決まりは `.claude/docs/web-db.md`。

`curl` では合言葉を環境変数のまま渡し、値を出さない。下の `$api` / `$h` は毎回のコマンドの頭で置く。

```
api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"
```

## 人物・話を引く

- その作品の話の並び(`start` 順)は一度に取る:
  `curl -sS -H "$h" "$api/api/tables/episode/records?story_id=<作品id>&sort=start&order=asc&limit=500" | jq -c '.items[] | {id, title, start, character_ids}'`
- 対象の話の本文: `curl -sS -H "$h" "$api/api/tables/episode/records/<episodeのid>" | jq -r '.record.main_text'`
- 本文に出る名前から人物 id を引く: `curl -sS -G -H "$h" "$api/api/tables/character/options" --data-urlencode 'q=<名>' | jq -c '.items[] | {id, label}'`
  (`q` は名前のほか本文にも当たるので、`label` を見て選ぶ)

## 回す

```
.venv/bin/python -c "
from data_access_logic.logs import configure_logging
from data_access_logic.episode.form import EpisodeForm
from web_session.episode import revise_episode
configure_logging()
episode = revise_episode(EpisodeForm(id=<episodeのid>), '''<直す指示>''', character_ids=[<人物id>, ...],
    model=None, effort=None)
print('EPISODE_ID', episode.id)
"
```

API に届かない(`ApiError`)・版が食い違うときは、`.venv/bin/python -m web_session.check_api` の出力をそのまま報告して止める
(見るところは `.docs/web-session.md` の「確かめる」の表)。

## 報告のために読む

`EPISODE_ID` の話を上の「対象の話の本文」の `curl` で読む(字数は `.record.letters`)。
