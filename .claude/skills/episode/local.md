# 手元での回し方(`CLAUDE_CODE_REMOTE` が `true` でない)

db の決まりは `.claude/docs/db.md`(転送が張れていないとき・版の食い違いもそこ)。
リポジトリのルートの `.venv` の python で回す(db は SessionStart フックが渡す `DEM_DATABASE_URL`)。

## id・話を引く

- 作品 id・人物 id・場所 id は db の `story` / `character` / `location` から引く(名前で頼まれたら `select id, name from ... where name like ...`)
- 同じ時刻の話が無いかは `episode` から引く(`select id, title, start from episode where story_id = <作品id> order by start`)

## 入口を呼ぶ

入口はどれも `<領域>.<ファイル>.<クラス>(...).show()` で呼ぶ(結果を JSON で出す)。

新しい話の枠を足す(`EPISODE_ID` を控える):

```
.venv/bin/python -c "
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
print('EPISODE_ID', CommitEpisode(EpisodeCommitForm(
    story_id=<作品id>, plot_text='''<プロット>''', start='<年/月/日>', character_ids=[<人物id>, ...])).run()['id'])
"
```

材料を読む(`<scratchpad>` はセッションのスクラッチパッド):

```
.venv/bin/python -c "
from data_access_logic.episode.read_episode_brief import ReadEpisodeBrief
ReadEpisodeBrief(<話id>).show()
" > <scratchpad>/brief_<話id>.json
```

設定を引く: `idea.resolve_terms.ResolveTerms([IdeaTerm(keyword=…, variants=[…], description=…, kind=…)], location_id=…, time='<話の時刻>')`
(`IdeaTerm` は `data_access_logic.idea.models`)。人物・場所を足す: `character.commit_character.CommitCharacter(CharacterCreateForm(...))` /
`location.commit_location.CommitLocation(LocationCreateForm(...))`(フォームは `data_access_logic/readme.md` の表)。

本文を確定する(本文はファイルから読む):

```
.venv/bin/python -c "
from pathlib import Path
from data_access_logic.episode.commit_episode import CommitEpisode
from data_access_logic.episode.form import EpisodeCommitForm
CommitEpisode(EpisodeCommitForm(
    id=<話id>, title='<題>', main_text=Path('<scratchpad>/episode_<話id>.txt').read_text(encoding='utf-8'),
    character_ids=[<人物id>, ...], location_id=<場所id>, viewpoint_character_id=<人物id>, synced=True)).run()
"
```

変えない欄は渡さない(渡した欄だけが直る)。設定を結ぶ: `idea.link_ideas.LinkIdeas([<アイデアid>, ...], episode_id=<話id>)`。

## 報告のために読む

話を db から読む(`select title, start, viewpoint_character_id, location_id, letters, summary_text from episode where id = <id>`)。
