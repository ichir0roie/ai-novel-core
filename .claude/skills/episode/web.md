# web のセッションでの回し方(`CLAUDE_CODE_REMOTE=true`)

db には繋がない。読むのは API の `curl`、書くのは入口と同じ処理の web の流れ(`web_session.episode.generate_episode`)で、
AI(`claude -p`)はこのセッションで回し、db の読み書きだけを API に頼む。決まりは `.claude/docs/web-db.md`。

`curl` では合言葉を環境変数のまま渡し、値を出さない。下の `$api` / `$h` は毎回のコマンドの頭で置く。

```
api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"
```

## id・話を引く

- 作品 id・人物 id・場所 id は名前から引く(`<表>` は `story` / `character` / `location`。`q` は名前のほか本文にも当たるので、`label` を見て選ぶ):
  `curl -sS -G -H "$h" "$api/api/tables/<表>/options" --data-urlencode 'q=<名>' | jq -c '.items[] | {id, label}'`
- 同じ時刻の話が無いかは、作品の話の並び(`start` 順)で確かめる:
  `curl -sS -H "$h" "$api/api/tables/episode/records?story_id=<作品id>&sort=start&order=asc&limit=500" | jq -c '.items[] | {id, title, start, letters}'`

## 回す

```
.venv/bin/python -c "
from data_access_logic.logs import configure_logging
from data_access_logic.episode.form import EpisodeForm
from web_session.episode import generate_episode
configure_logging()
episode = generate_episode(EpisodeForm(
    story_id=<作品id>, plot_text='''<話のプロット>''', start='<年/月/日>', character_ids=[<人物id>, ...],
    location_id=None, viewpoint_character_id=None))
print('EPISODE_ID', episode.id)
"
```

本文の無い話へ書くときは `EpisodeForm(id=<episodeのid>, character_ids=[<人物id>, ...])`(`character_ids` は省いてよい)。
モデルを変えるときは `generate_episode(..., model='claude-fable-5-1', effort='high')`。

API に届かない(`ApiError`)・版が食い違うときは、`.venv/bin/python -m web_session.check_api` の出力をそのまま報告して止める
(見るところは `.docs/web-session.md` の「確かめる」の表)。

## 報告のために読む

`curl -sS -H "$h" "$api/api/tables/episode/records/<EPISODE_ID>" | jq '.record | {title, start, viewpoint_character_id, letters, main_text}'`
(あらすじは本文から短くまとめる)。
