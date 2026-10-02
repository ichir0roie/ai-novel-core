# 手元での回し方(`CLAUDE_CODE_REMOTE` が `true` でない)

入口の呼び方は `.claude/skills/episode/local.md` のとおり。ここには推敲で違う所だけを書く。

## 話を引く

- 作品の話の並びは `episode.read_episodes.ReadEpisodes(story_id, count=..., text=False)` で一度に取る。`start` 順で返るので、並びを確かめる select を別に打ち直さない
- 「エピソード5」のような番号は、この並びの順で数える

## 確定する

本文に加えて `plot_text` と `synced` を渡す:

```
.venv/bin/python -c "
from pathlib import Path
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
CommitEpisode(EpisodeCommitForm(
    id=<話id>, main_text=Path('<scratchpad>/episode_<話id>.txt').read_text(encoding='utf-8'),
    plot_text=Path('<scratchpad>/plot_<話id>.txt').read_text(encoding='utf-8'), synced=<True|False>)).run()
"
```

## 報告のために読む

話を db から読む(`select title, letters, location_id from episode where id = <id>`)。
