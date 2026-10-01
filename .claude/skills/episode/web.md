# web のセッションでの回し方(`CLAUDE_CODE_REMOTE=true`)

db には繋がない。読むのは API の `curl`、入口は web の流れ(`web_session.flows.run`)で呼ぶ。claude を叩く入口
(`ReadEpisodeBrief` の要約の作り直し・`CommitEpisode` の概要・ミーム)は AI をこのセッションで回し、db の読み書きだけを API に頼む。
db だけの入口(`ReadEpisodeCasting`・`ReadEpisodeTexts`・`RefreshMentions`・`CastEpisode`・`ResolveTerms`・`CommitCharacter`・`CommitLocation`・`LinkIdeas`)は同じ `run` でそのまま API に流れる。決まりは `.claude/docs/web-db.md`。

`curl` では合言葉を環境変数のまま渡し、値を出さない。下の `$api` / `$h` は毎回のコマンドの頭で置く。

```
api="${NOVEL_API_URL%/}"; h="x-novel-api-key: $NOVEL_API_KEY"
```

## id・話を引く

- 作品 id・人物 id・場所 id は名前から引く(`<表>` は `story` / `character` / `location`。`q` は名前のほか本文にも当たるので、`label` を見て選ぶ):
  `curl -sS -G -H "$h" "$api/api/tables/<表>/options" --data-urlencode 'q=<名>' | jq -c '.items[] | {id, label}'`
- 同じ時刻の話が無いかは、作品の話の並び(`start` 順)で確かめる:
  `curl -sS -H "$h" "$api/api/tables/episode/records?story_id=<作品id>&sort=start&order=asc&limit=500" | jq -c '.items[] | {id, title, start, letters}'`

## 入口を呼ぶ

入口はどれも、入口の id と引数(JSON の形。フォームは dict で書く)で呼ぶ:

```
.venv/bin/python -c "
import json
from data_access_logic.logs import configure_logging
from web_session.flows import run
configure_logging()
print(json.dumps(run('<入口の id>', {<引数>}), ensure_ascii=False, indent=2))
"
```

| すること | 入口の id | 引数 |
| --- | --- | --- |
| 新しい話の枠を足す | `episode.commit_episode.CommitEpisode` | `{'episode': {'story_id': …, 'plot_text': '''…''', 'start': '<年/月/日>', 'character_ids': […]}}` |
| 登場人物・場所を決める材料を読む | `episode.read_episode_casting.ReadEpisodeCasting` | `{'episode_id': …}` |
| 話を id で読む(本文まで) | `episode.read_episode_texts.ReadEpisodeTexts` | `{'episode_ids': […]}`。長いので `> <scratchpad>/texts.json` へ書き出して Read する |
| 名前だけ出る人物を拾い直す | `episode.refresh_mentions.RefreshMentions` | `{}`(すべての話)か `{'episode_ids': […]}` |
| 登場人物・場所・視点を結ぶ | `episode.cast_episode.CastEpisode` | `{'episode_id': …, 'character_ids': […], 'location_id': …, 'viewpoint_character_id': …}` |
| 本文の材料を読む(結んだあと) | `episode.read_episode_brief.ReadEpisodeBrief` | `{'episode_id': …}`。出力を `> <scratchpad>/brief_<話id>.json` へ書き出して Read する |
| 設定を引く | `idea.resolve_terms.ResolveTerms` | `{'terms': [{'keyword': …, 'variants': […], 'description': …, 'kind': …}], 'location_id': …, 'time': '<話の時刻>'}` |
| 人物を足す | `character.commit_character.CommitCharacter` | `{'character': {'name': …, 'start': …, 'location_id': …, 'histories': [{'description': <説明>}, {'start': <年の整数>, 'description': <来歴の節目>}]}}` |
| 人物の来歴を読む | `character.read_character.ReadCharacter` | `{'character_id': …}`(時刻を渡さず、すべての行を読む) |
| 人物の来歴に足す | `character.update_character.UpdateCharacter` | `{'character': {'id': …, 'histories': [<今の行すべて。話の年の行があればその説明に書き足す>, {'start': <話の年の整数>, 'description': …}]}}` |
| 場所を足す | `location.commit_location.CommitLocation` | `{'location': {'name': …, 'kind': …, 'text': …, 'parent_id': …}}` |
| 本文を確定する | `episode.commit_episode.CommitEpisode` | 下の例 |
| 設定を結ぶ | `idea.link_ideas.LinkIdeas` | `{'idea_ids': […], 'episode_id': …}` |

本文を確定する(本文はファイルから読む。変えない欄は渡さない):

```
.venv/bin/python -c "
from pathlib import Path
from data_access_logic.logs import configure_logging
from web_session.flows import run
configure_logging()
record = run('episode.commit_episode.CommitEpisode', {'episode': {
    'id': <話id>, 'title': '<題>', 'main_text': Path('<scratchpad>/episode_<話id>.txt').read_text(encoding='utf-8'),
    'synced': True}})
print('EPISODE_ID', record['id'], record['letters'])
"
```

API に届かない(`ApiError`)・版が食い違う・段が無いと返るときは、`.venv/bin/python -m web_session.check_api` の出力をそのまま報告して止める
(見るところは `.docs/web-session.md` の「確かめる」の表)。

## 報告のために読む

`curl -sS -H "$h" "$api/api/tables/episode/records/<EPISODE_ID>" | jq '.record | {title, start, viewpoint_character_id, location_id, letters, main_text}'`
(あらすじは本文から短くまとめる)。
