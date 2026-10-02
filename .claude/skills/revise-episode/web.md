# web のセッションでの回し方(`CLAUDE_CODE_REMOTE=true`)

入口の呼び方は `.claude/skills/episode/web.md` のとおり。ここには推敲で違う所だけを書く。

## 話を引く

作品の話の並び(`start` 順)は一度に取る。「エピソード5」のような番号は、この順で数える:
`curl -sS -H "$h" "$api/api/tables/episode/records?story_id=<作品id>&sort=start&order=asc&limit=500" | jq -c '.items[] | {id, title, start, character_ids}'`

## 確定する

本文に加えて `plot_text` と `synced` を渡す:

```
.venv/bin/python -c "
from pathlib import Path
from data_access_logic.logs import configure_logging
from web_session.flows import run
configure_logging()
record = run('episode.commit_episode.CommitEpisode', {'episode': {
    'id': <話id>, 'main_text': Path('<scratchpad>/episode_<話id>.txt').read_text(encoding='utf-8'),
    'plot_text': Path('<scratchpad>/plot_<話id>.txt').read_text(encoding='utf-8'), 'synced': <True|False>}})
print('EPISODE_ID', record['id'], record['letters'])
"
```

## 報告のために読む

`curl -sS -H "$h" "$api/api/tables/episode/records/<EPISODE_ID>" | jq '.record | {title, letters, location_id, character_ids}'`
