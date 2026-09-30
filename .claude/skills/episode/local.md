# 手元での回し方(`CLAUDE_CODE_REMOTE` が `true` でない)

db の決まりは `.claude/docs/db.md`(転送が張れていないとき・版の食い違いもそこ)。

## id・話を引く

- 作品 id・人物 id・場所 id は db の `story` / `character` / `location` から引く(名前で頼まれたら `select id, name from ... where name like ...`)
- 同じ時刻の話が無いかは `episode` から引く(`select id, title, start from episode where story_id = <作品id> order by start`)

## 回す

リポジトリのルートの `.venv` の python で回す(db は SessionStart フックが渡す `DEM_DATABASE_URL`)。

```
.venv/bin/python -c "
from data_access_logic.episode.form import EpisodeForm
from data_access_logic.episode.generate_episode import GenerateEpisode
episode = GenerateEpisode(EpisodeForm(
    story_id=<作品id>, plot_text='''<話のプロット>''', start='<年/月/日>', character_ids=[<人物id>, ...],
    location_id=None, viewpoint_character_id=None)).run()
print('EPISODE_ID', episode['id'])
"
```

本文の無い話へ書くときは `EpisodeForm(id=<episodeのid>, character_ids=[<人物id>, ...])`(`character_ids` は省いてよい)。
モデルを変えるときは `GenerateEpisode(..., model='claude-fable-5-1', effort='high')`。

## 報告のために読む

`EPISODE_ID` の話を db から読む(`select title, start, viewpoint_character_id, letters, summary_text from episode where id = <id>`)。
