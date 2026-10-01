# web のセッションでの回し方(`CLAUDE_CODE_REMOTE=true`)

入口の呼び方(材料を読む・本文を確定する・人物と場所を足す)は `.claude/skills/episode/web.md` のとおり。ここには推敲で違う所だけを書く。

## 話を引く

- その作品の話の並び(`start` 順)は一度に取る。「エピソード5」のように番号で頼まれたら、この順で数える:
  `curl -sS -H "$h" "$api/api/tables/episode/records?story_id=<作品id>&sort=start&order=asc&limit=500" | jq -c '.items[] | {id, title, start, character_ids}'`

## 確定する

本文に加えて、`plot_text`(「## 推敲」の節に指示を足したもの)と `synced`(材料の「同期」の値)を渡す:

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
