# 手元での回し方(`CLAUDE_CODE_REMOTE` が `true` でない)

db の決まりは `.claude/docs/db.md`(転送が張れていないとき・版の食い違いもそこ)。

## 人物・話を引く

- その作品の話の並びは `episode.read_episodes.ReadEpisodes(story_id, count=..., text=False)` で一度に取る
  (`start` 順で返るので、並びを確かめる select を別に打ち直さない)
- 対象の話の本文に出る名前から人物 id を引く(`select id, name from character where name like '%<名>%'`)

## 回す

リポジトリのルートの `.venv` の python で回す(db は SessionStart フックが渡す `DEM_DATABASE_URL`)。

```
.venv/bin/python -c "
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.revise_episode import ReviseEpisode
episode = ReviseEpisode(EpisodeForm(id=<episodeのid>), '''<直す指示>''', character_ids=[<人物id>, ...],
    model=None, effort=None).run()
print('EPISODE_ID', episode['id'])
"
```

## 報告のために読む

`EPISODE_ID` の話を db から読む(`select title, letters, main_text from episode where id = <id>`)。
