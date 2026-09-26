claude が db を触るときに呼ぶ入口を置く場所。**操作前にこの readme を引く。**

各ファイルは**一つの呼び出しクラスだけ**を持つ。呼び出し側(claude)は、
そのクラスをインスタンス化して `run()` を呼ぶだけでよい
(CLI 引数のパースはしない。`if __name__ == "__main__"` も置かない)。

    from ai.claude_code.interface.world.list_places import ListPlaces
    ListPlaces(kind="村").run()

db の触り方(入口越し・読み取り・md との同期)は CLAUDE.md の「db への接続」「md と db の同期」を見る。

## 依頼内容 → 呼ぶコード

`ai.claude_code.interface.` を頭に付けて import する。

| 依頼内容(言い回しの例)           | 呼ぶコード                                                                 |
| ---------------------------------- | -------------------------------------------------------------------------- |
| 「同期して」「sync_db」             | `sync.sync_db.SyncDb()`。手で直された md だけを取り込み、手で消された md の行を db から消し(md に出さない要約・中間テーブル・子の行も一緒に消す。残っている他の md の行が指していれば止まる)、db と食い違う md だけを書き直す。`{"imported", "deleted", "conflicts", "written", "removed"}` を返す。`deleted` は手で消されて行を消した md、`conflicts` は md と db の両方で直されていて md を勝たせたもの。`# data` の無い手書きの md は、md 名を `filename` のほか場所・人物・アイデア・作品の `name` にも使い、種別(`kind`)の無いアイデアは AI が既にある種別から選んで付ける(応答が使えなければ「概念」)。取り込み・書き出しを片方だけ回すなら `sync.import_db.ImportDb()` / `sync.export_db.ExportDb()`(手で直された・消された md が残っていれば止まる。`ExportDb(force=True)` で押し切る) |
| 「どんな場所がある?」「村の一覧」   | `world.list_places.ListPlaces(kind=None)`                                    |
| 「この場所の近くには何がある?」     | `world.list_neighbors.ListNeighbors(place_id, kind=None, limit=None)`。同じ星の他の場所の方角・距離・高低差を近い順に返す |
| 「人物の一覧」「誰がいる?」         | `world.list_characters.ListCharacters()`                                     |
| 「人物同士の関係は?」               | `world.list_character_relations.ListCharacterRelations(character_id=None)`   |
| 「出来事の一覧」                     | `world.list_events.ListEvents()`(全件)。絞るなら `story.read_events.ReadEvents(time=…)` か、`ReadEvents(place_id=…)` / `ReadEvents(character_id=…)` / `ReadEvents(event_id=…)`(どの表の id かを名前で渡す) |
| 「このアイデアは何?」「アイデアを調べて」 | `world.search_ideas.SearchIdeas(keywords, place_id=None, limit=None, time=None)`。名前・本文の部分一致のあいまい検索。`keywords` は語一つか、`{"keyword", "variants"}`(言い換え)のリスト。当たり方の強い順に返す。自動生成の候補も返す。`place_id` は現在地から最上位までの場所に、`time` はその時刻に効く(`start` <= time < `end`)アイデアに絞る。`called` はその場所・時刻での作中の呼び名 |
| 「この下書きに関わる設定は?」(中間段を自分で回す) | `idea.resolve_terms.ResolveTerms(terms, place_id=None, time=None)`。下書きから洗い出した語(`{"keyword", "variants", "description", "kind", "start", "end"}`)をアイデアと照らし、当たったものと上位・下位を返す。当たらなかった語は候補として足す(下の「中間段」)。候補の効く期間は語の `start` / `end`。`start` は `time` と下書きの中身からある程度はっきり言えるときだけ付け(言えなければ省いて None)、`end` は分かるときだけ付ける。`time` は出来事の時刻。`time` を渡すと `start` が空(時期が未定)のアイデアは `ideas` に入れない。呼び名に当たったら本質のアイデアにそろえ、作中の呼び名を `called` に付ける |
| 「この本文が踏まえたアイデアを結んで」 | `idea.link_ideas.LinkIdeas(idea_ids, event_id=None, episode_id=None, character_id=None)`。三つのうち一つだけ渡す |
| 「この候補をあのアイデアにまとめて」 | `randomizer.merge_idea.MergeIdea(source_id, target_id)`。結んだ本文と source の呼び名を付け替えてから source を消す |
| 「判断待ちの一覧」「週次レビュー」   | `review.list_pending_reviews.ListPendingReviews()`。候補・未同期の話・本文に残った TODO。Todoist へ載せる手順はスキル `weekly-review` |
| 「場所を足して」                     | `randomizer.create_random_place.CreateRandomPlace()` で下書き → 内容を決めて `randomizer.commit_place.CommitPlace(place)` |
| 「人物を足して」                     | `randomizer.create_random_character.CreateRandomCharacter()` → `randomizer.commit_character.CommitCharacter(character)`。持たせるミームは `meme.draw_memes.DrawMemes(person=True)` で引き、`text` の `# meme` 節と `# 行動原理` 節に書く(下の「人物が持つミーム」)。`# 来歴` 節には節目を歳付きで書く(下の「人物の来歴」) |
| 「この場所にランダムな人物を何人か作って」「全国家に人物を生成」 | `randomizer.generate_characters.GenerateCharacters(place_ids, time, count=(2, 4), person=True, seed=None)`。場所ごとに `count` の範囲の人数を、時の流れの中で生む人物と同じ自動生成(`_generate_one`。性格・ミーム・来歴・名づけまで AI が決める)で作り、`time` の時点で生まれた歳にする。一人ごとに commit する。作品の無い場所が混ざっていれば作る前に止まる。`person=False` で人物以外の対象を作る |
| 「出来事を足して」                   | `randomizer.create_random_event.CreateRandomEvent()` → `randomizer.commit_event.CommitEvent(event)` |
| 「この人物の出自・居場所を足して」   | `randomizer.commit_character_place.CommitCharacterPlace(place)`              |
| 「この二人の相関を足して」           | `randomizer.commit_character_relation.CommitCharacterRelation(relation)`     |
| 「アイデアを足して」                 | `randomizer.commit_idea.CommitIdea(idea, fact_check=True)`。効く場所は `location_id`(その場所と配下で効く)、効く期間は `start` / `end`(出来事の時刻と比べる。空なら限らない)。確定したあと、AI が Dラボのナレッジとネット検索でアイデアの妥当性・補足を検め、`fact_check` 欄(md の `# fact_check` 節)へ書く。続けて本文と検証結果のそれぞれからミームを抜き出し(`memes_added`)、足したミームも検める。`fact_check=False` で検めずに本文からだけ抜き出す |
| 「作中での呼び名を足して」「この場所・時代では〇〇と呼ぶ」 | `randomizer.commit_idea.CommitIdea(idea)` に `alias_of_idea_id`(本質のアイデア)を付けて足す。呼び名を使う場所・時代は `location_id` / `start` / `end`(空の列はどこでも・いつでも)。清書・断面・検索は、場所・時代が当てはまる呼び名のうち場所の近いものを選んで本質のアイデアをその名で呼び、当てはまらなければ本質の `name` を使う。呼び名の呼び名は持てない |
| 「アイデア・oracle・ミームを検めて」「妥当性を調べて」 | `fact_check.check_facts.CheckFacts(table, ids=None, limit=None)`。`table` は `"idea"` / `"oracle"` / `"meme"`。AI が Dラボのナレッジ(優先)とネット検索で妥当性と補足を書き、`fact_check` 欄へ入れる。`ids` を省くと `fact_check` が空のものすべて(`limit` で件数を絞る)、渡すと検め済みでも検め直す。アイデア・oracle は検めたあと本文と検証結果からミームを抜き出し直し、足したミームも検める。`{"checked", "memes_added"}` を返す |
| 「場所を直して」                     | `randomizer.update_place.UpdatePlace(place)`                                 |
| 「この人物の〇歳からの名字・背丈・口調・性格を決めて」「結婚して名字が変わる」 | `randomizer.update_character.UpdateCharacter({"id": …, "parameters": [...]})`。期間ごとの行の配列をまるごと渡す(下の「期間ごとのパラメータ」)。今の配列は `ReadCharacter` の `parameters` で読める |
| 「人物を直して」                     | `randomizer.update_character.UpdateCharacter(character)`。名字・体格・口調・性格は `parameters` に入れる(渡さなければ触らない)。出自・居場所は `randomizer.update_character_place.UpdateCharacterPlace(place)`、相関は `randomizer.update_character_relation.UpdateCharacterRelation(relation)` |
| 「場所を消して」                     | `randomizer.delete_place.DeletePlace(place_id)`                              |
| 「出来事を直して」                   | `randomizer.update_event.UpdateEvent(event)`。`id` 必須、渡した欄だけ直す。当事者は変えない。直したあと要約(`event_summary`)を作り直す |
| 「出来事を消して」「出来事を作り直して」 | `randomizer.delete_event.DeleteEvent(event_id)`。子の出来事が残っていれば止まる。当事者・アイデアとの中間テーブルの行と要約も消す。出来事で人物の `text` に積み足した一文と、足したアイデアの候補は残るので、要らなければ `UpdateCharacter` / `DeleteIdea` で別に戻す |
| 「アイデアを直して」                 | `randomizer.update_idea.UpdateIdea(idea)`。`id` 必須、渡した欄だけ直す       |
| 「アイデアを消して」                 | `randomizer.delete_idea.DeleteIdea(idea_id)`。下位のアイデアか呼び名が残っていれば止まる。結んだ本文との中間テーブルの行も消す |
| 「覚え書きを足して」「oracle に書いて」 | `randomizer.commit_oracle.CommitOracle(oracle, fact_check=True)`。`text` 必須。置き場所は `directory_path`(`worlds/oracle/` からの相対)と `filename` で決める。確定したあとは `CommitIdea` と同じく、検めて(`fact_check`)、本文と検証結果のそれぞれからミームを抜き出し(`memes_added`)、足したミームも検める |
| 「覚え書きを直して」                 | `randomizer.update_oracle.UpdateOracle(oracle)`。`id` 必須、渡した欄だけ直す |
| 「ミームを直して」「ミームの分類を直して」 | `randomizer.update_meme.UpdateMeme(meme)`。`id` 必須、渡した欄だけ直す。`category` は 信条/欲求/境遇/集団/理 のいずれか |
| 「ミームを消して」                   | `randomizer.delete_meme.DeleteMeme(meme_id)`                                 |
| 「出来事の種を直して」               | `randomizer.update_event_seed.UpdateEventSeed(seed)`。`id` 必須、渡した欄だけ直す。種は md に出ないので、語の置き換えなどは db を読んで id を拾ってから呼ぶ |
| 「ミームを抜き出して」               | `meme.extract_memes.ExtractMemes()`。アイデア・oracle(`worlds/oracle/` の著者の覚え書き)の本文と検証結果(`fact_check`。別々の元として渡す)・人物の筋書き(`# plot`)・出来事の本文から抜き出し、分類を振って `meme` テーブルへ足す(md は分類のディレクトリ `worlds/meme/<分類>/` に置く)。既にあるミームと同じ考え方の言い換えは足さない。最後に、分類の空いたミーム(md に直接書いたものなど)に分類を振り、置き場所の無いものは分類のディレクトリへ置く。足したミームは AI が Dラボのナレッジとネット検索で検め、`fact_check` 欄へ書く(`ExtractMemes(fact_check=False)` で飛ばす)。足した件数を返す |
| 「ミームを引いて」                   | `meme.draw_memes.DrawMemes(person=True, seed=None)`。分類ごとに 0〜2 件引き、それぞれに古今表裏を割り振って返す。db には書かない |
| 「ミームと要約の取りこぼしをまとめて作って」 | `meme.refresh_generated_content.RefreshGeneratedContent()`。`ExtractMemes` に加えて、まだ要約の無い出来事・話もすべて見て `event_summary` / `episode_summary` を作る。`CommitEvent` / `CommitStory` / `CommitEpisode` は確定した一件だけを見るので、md を直接編集して `import_db` した分などの取りこぼしを拾うのはこちら |
| 「作品の一覧」                       | `story.list_stories.ListStories()`                                           |
| 「話を書き始める」「次の話を書く」   | `story.start_story.StartStory(story_id)`。同期確認・見出し・直前の話・断面・顔ぶれを一度に出す |
| 「前の話を読ませて」                 | `story.read_episodes.ReadEpisodes(story_id, count=10, before=None, text=True)`。`before` は時刻で、start がそれより前の話に絞る |
| 「その時点の顔ぶれは?」             | `story.read_cast.ReadCast(story_id, time=None)`                              |
| 「その場所・その時点の様子は?」     | `story.read_brief.ReadBrief(place_id, time)`                                 |
| 「この人物の周りで何が起きている?」 | `story.read_surroundings.ReadSurroundings(character_id, time)`               |
| 「この人物を本文用にそろえて」       | `story.read_character.ReadCharacter(character_id, time=None)`。体格・口調・性格は `time` の時点の値を上の段に出す(`time` を省くと期間を限らない値だけ)。期間ごとの行は `parameters` |
| 「作品を作る」「筋書きを足して」     | `story.commit_story.CommitStory(story)`。筋書きは作品の `text` に書く        |
| 「作品を直して」「筋書きを直して」   | `story.update_story.UpdateStory(story)`                                      |
| 「作品を消して」                     | `story.delete_story.DeleteStory(story_id)`。話が残っていれば止まる           |
| 「本文を確定する」「話の種を入れる」 | `story.commit_episode.CommitEpisode(episode)`。`id` を渡せばその話を直し(渡した欄だけ)、省けば `story_id` の作品に新しい話を足す。`key`(種)か `text`(本文)のどちらかがあればよい。`text` は `ai/instructions/style.py` の `layout_novel_text` で改行を整えてから入れる(地の文は一文一行、「◇」の行は空行二つ)。話に番号は無く、作品の中では `start` の順に並ぶ(`start` の無い話は後ろに id 順)。あいだに話を足すときは、前後の話のあいだの `start` を付ける |
| 「未同期の話は残ってる?」           | `story.list_unsynced_episodes.ListUnsyncedEpisodes(story_id=None)`           |
| 「世界観へ反映済みにする」           | `story.set_episode_synced.SetEpisodeSynced(episode_id, synced=True)`   |
| 「世界を進めて」「ループを回して」   | 入口ではなく常駐ループ。「常駐ループ」を見る                                  |
| 「毎日のルーチン」「サブキャラの次の出来事を起こして」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `daily_event`。主役を決めるなら `character_id` を渡す。「〇〇の17歳の出来事」のように歳を決めるなら `age` も渡す(直前の出来事の後ではなく、その歳のうちに差し込む) |
| 「この場所・この時の出来事を起こして」「ヴァレンツァで11579/03/02に〇〇な場面」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `place_event`。場所 id・時刻・`key`(ジャンルや場面を一言で)を渡す。当事者はその時刻にそこにいるサブキャラクターから選ぶ |
| 「この種で話を書いて」「〇〇と△△が出る話を 11579/03/02 で」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `episode`。作品 id・`key`(話の種)・時刻・登場人物の id のリストを渡す。前の話を名指しするなら `previous_episode_ids`(省けば作品の中でその時刻より前の三話)。場所・視点を決めるなら `place_id` / `viewpoint`。題・時刻だけ決めた本文の無い話(枠)へ書くなら `episode_id`(種・時刻・視点・題は省けば枠のもの) |

**まだ入口が無いもの**(頼まれたら作ってから行う): 人物の削除。

筋書き(`plot` / `character_plot`)のテーブルは無い。場所に掛かる筋書きは作品(`story`)の
`text` に、人物に掛かる筋書きはその人物の `text` の `# plot` の節に書く。

**期間ごとのパラメータ**: 人物の名字(`family_name`)・体格(`sex` `height` `build`)・口調(`first_person` `second_person` `third_person` `tone` `dialect`)・
性格(12 軸。無/低/並/高/必)は、`character_parameter` テーブルに期間ごとの行で持つ。md では人物の `# data` の
`parameters` に配列で並ぶ(id と character_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。

```json
"parameters": [
  {"start": null, "end": null, "height": 140.0, "tone": "負けず嫌いで声が大きい", "sincerity": "並", ...},
  {"start": "11600", "end": null, "height": 175.0, "tone": null, ...}
]
```

- `start` / `end` が空なら、その端は限らない。両方空の行は全期間に効く。`end` の時刻からは効かない
- 空の欄は「この期間では決めない」。ある時刻の値は、その時刻に掛かる行を、期間を限らない行から順に重ねて決める
  (限る端の多い行、同じなら `start` の遅い行、それも同じなら後の行が勝つ)。どの行も決めていない性格の軸は「並」
- 時刻を渡さずに引くと、期間を限らない行だけを重ねる
- 生成(毎日のルーチン・出来事の進行)は、出来事の時刻の値を使う。人物の自動生成・`CreateRandomCharacter` は期間を限らない一行だけを作る
- `CommitCharacter` / `UpdateCharacter` は `parameters` を受け取る。`UpdateCharacter` に渡すと配列をまるごと置き換える
- `name` は名字を含めない名だけを持つ。名字は `family_name` に分け、結婚・養子・家の取り立てなどで変わるなら、
  変わった時点からの行を足す。名字を持たない身分なら空。`CreateRandomCharacter` の下書きでは空なので、
  出自・身分・土地柄から決めて入れる(時の流れの中で生む人物は、名づけのときに AI が決める)

人物の来歴は、その人物の `text` の `# 来歴` 節に、節目を `- <年>年(<歳>歳): <何があり、立場・仕事・住まい・人間関係がどう変わったか>`
の箇条書きで、歳の順に書く。人物説明にある立場・仕事・住まいには、いつそうなったかの節目を必ず入れる。
「現在」の行は要らない。出来事の生成は、この歳と age を見比べてその時点の段階
(子ども・見習い・一人前など)を決めるので、後年の立場を先取りしないための手がかりになる。
`# 来歴` は `# meme` より前に置く。

人物が持つミーム(行動原理の芯。`meme` テーブル)も専用の節は無く、その人物の `text` の
`# meme` 節に、持つミームの文面を `- <古今表裏>: <文面>` の箇条書きでそのまま書く。
人物は複数のミームを持ってよい。ミームどうしの関係の整理は、`# meme` ではなく `# 行動原理` 節に書く
(`# plot` に書くと、そこからミームがまた抜き出される)。

- 古今表裏: 古=かつて持っていたが今は手放した / 今=いま持っている / 表=人前で掲げている / 裏=内に秘めている
- 引き方: 分類ごとに 0〜2 件。人物は 信条・欲求・境遇、人物以外の対象は 信条・欲求・集団 から引く。
  理(世界の法則)は引かない(`ai/time_keeper/constants.py` の `MEME_*`)
- 時の流れの中で生む人物(`ai/time_keeper/random_character_generator.py`)は、この引き方と整理を自動で行う

## 中間段(下書き → 語の洗い出し → 清書)

本文を書く生成は、下書き(一段目)と清書(二段目)のあいだに、アイデアと照らす中間段を挟む
(`ai/time_keeper/idea_context.py`)。

1. 下書きから、設定資料と照らす語とその言い換えを AI に挙げさせる(`idea_search.keywords_of`)。
   出来事の時刻と下書きの中身から、語ごとの `start` / `end` も決めさせる。ある程度はっきりした `start` が言えない語は null、`end` は分かる語だけ
2. 語と言い換えで、アイデアの名前・本文を部分一致で引く(`idea_search.search`)。その場所・時刻で効くアイデアだけ。
   場所は、アイデアの `location_id` が現在地から最上位までの場所のどれかに当たるもの。
   時刻は、出来事の時刻が `start` 以上 `end` 未満のもの(`end` が空なら限らない)。
   `start` が空のアイデアは時期が未定で、その時刻にもうあるかが分からないので、語が当たっても清書に渡さない(候補も足さない)。
   当たったアイデアに上位・下位のアイデアを足して、清書に「関係する設定」として渡す
3. どのアイデアにも当たらなかった語は、AI が決めた種別(`kind`)と `auto_generated=true` で、種別のディレクトリ(`worlds/idea/<kind>/`)に足す。
   場所は世界線、`start` / `end` は 1. で決めたもの(null ならそのまま空。時期が未定の候補になる)。候補も他のアイデアと同じく検索・断面・清書・ミームの抜き出しに出る。
   確かめたら `auto_generated` を false にする
4. 下書きが当たったアイデアと候補を、清書したレコードに中間テーブル(`event_idea` / `episode_idea` /
   `character_idea`。md には出さない)で結ぶ

| 生成 | 下書き | 清書 |
| ---- | ------ | ---- |
| 毎日の出来事 | 記録(`_progress_place`) | 小説の本文(`_novelize`) |
| 人物の自動生成 | 中身を決めた説明 | 関係する設定があれば説明を清書 |
| 話の自動生成(`story_writer`) | 種(`key`) | 本文 |

claude が対話で書くときは、自分で語と言い換えを挙げて `ResolveTerms` を呼び、返った `ideas` を踏まえて清書し、
確定したあとに `hits` と `candidates` の id を `LinkIdeas` で結ぶ。

`meme` テーブル自体はアイデア(`idea`)・oracle・人物の筋書き・出来事から抜き出して貯めるだけで、
人物との FK は持たない(ミームは人物の間を移り変わり・伝染していくため)。

補足:

- `CommitEvent` / `CommitStory` / `CommitEpisode` は、確定したあとに毎回
  `ai/time_keeper/generated_content.py` の `refresh` を自分で呼ぶ。ミームの棚卸し
  (`meme.refresh`)と、出来事・話ならその場での要約(`event_summary` / `episode_summary`)を
  まとめて行うので、`ExtractMemes` を別に呼ぶ必要は無い。確定の入口を通らなかった分の
  取りこぼしをまとめて拾いたいときは `RefreshGeneratedContent` を呼ぶ。これらの経路で足したミームは
  検めない(`fact_check` が空のまま)ので、`CheckFacts("meme")` で後から埋める
- 話(`episode`)の md だけは `# data` `# key` `# text` の三節を持つ。`# key` は作者が
  入れる種(AI 生成前)、`# text` は AI か作者が書く、投稿する本文。時期・場所・視点は
  `# data` の `start` / `end` / `place` / `viewpoint` に入る。md の名前は `{story_id}_{start}_{title}.md`
  (start は `年-月-日-時分`。start の無い話は `{story_id}__{title}.md`)。同じ日の話は時分で並べ分ける
- 本文は一話 5000〜8000 字(`ai/instructions/style.py` の `EPISODE_TARGET_LETTERS`)。
  場面の数と一場面の長さは決めず、中身に合わせる。**書く直前に種を場面まで割ってから本文に入る**。種はその話ぶんで 300〜500 字を目安に、
  `## 場面` の箇条書き(`場所 / 出る人 / そこで変わること`)と `## 狙い` で書く:

```
# key
## 場面

1. エンピレオ 面会室 / ミレア・カシル / カシルが原初型の中身を明かす
2. 住まい / ミレア / 追放と遺伝凍結処理の通達が届く
3. 住まい / ミレア・ノア / 四歳のノアの身体と白い灯りを見せる
4. 住まい 夜 / ミレア・アウレア・ピリム / 外装を出す。アウレアが頼みごとをする
5. 都の縁 → 地上 / ミレア・ノア・ピリム / 落ちる。ローザ諸都市同盟に着く

## 狙い

前日譚をここで閉じる。父の顔は最後まで見せない。
```
- `SyncDb` / `ExportDb` は md の写しに加えて、星ごとの地図 `{id}_map.svg`・`../worlds/maps/map.html`・
  人物相関の `../worlds/maps/relation.html` も描く。`ImportDb` は md → db の逆向き
- 場所の輪郭は `polygon` 欄(GeoJSON の Polygon。`[[経度, 緯度], ...]` の環を渡せば
  閉じて揃える)で `CommitPlace` / `UpdatePlace` から入れる。経緯度が無い面の場所
  (大陸など)にも持たせられ、地図では薄い面として描く

## 常駐ループ

世界の生成(出来事・人物・場所・本文)は主に `ai/local_ai/` の常駐ループが行う。
その起動だけは運用タスクとして直接呼んでよい。

| したいこと                                   | ローカル AI                                | Claude Code                                                        |
| -------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------ |
| 時間を進める                                 | `local_ai_time_keeper.loop_time()`         | `claude_code_time_keeper.claude_main()` / `story_writer.write_story()` |
| ある作品の開始から指定年数ぶん進める         | `local_ai_time_keeper.loop_time_for_story()` | `claude_code_time_keeper.claude_story_years_main()`               |
| サブキャラ一人の次の出来事を一件起こす(毎日のルーチン) | `local_ai_time_keeper.daily_event()`       | `claude_code_time_keeper.claude_daily_event_main()`                |
| ある場所・時刻に、居合わせるサブキャラで出来事を一件起こす(場面を指定) | `local_ai_time_keeper.place_event(place_id, time, key)` | `claude_code_time_keeper.claude_place_event_main(place_id, time, key)` |
| 種・時刻・登場人物を決めて、作品に話を一話足す(`episode_id` で既存の枠へ書く) | `local_ai_time_keeper.episode(story_id, key, time, character_ids, previous_episode_ids=None, episode_id=None)` | `claude_code_time_keeper.claude_episode_main(story_id, key, time, character_ids, previous_episode_ids=None, episode_id=None)` |

(`ai.local_ai.` / `ai.claude_code.` を頭に付ける)

毎日のルーチンは、人物ごとに生まれてから 5〜20 年後を起点に自分の時を刻む。作品の時期には合わせず、
作品の本文(筋書き)も渡さない。出来事の候補は、出来事の種(`event_seed` テーブル。md には出さない)から
ランダムに引いた種か、直前の出来事からの連想で立てる。種は作品の本文・話の種(`key`、無ければ本文)・
人物の `# plot` の節・出来事の本文から、時代・場所・固有名詞を抜いて抜き出したもの。ルーチンの頭で、
`event_seeded` が false の元だけから抜き出して true にする(`ai/time_keeper/event_seed.py`)。
抜き出しは元ごとに一度だけ。本文を書き直して抜き出し直したいときは、その md の `event_seeded` を false に戻す。
抜き出すときは似た種があるかを見ない。棚卸し前(`consolidated` が false)の種が 50 件たまったら、ルーチンの頭で
AI に棚卸し済みの種と見比べさせ、同じ出来事の言い換えだけをまとめる(`event_seed.consolidate`)。
人物ごとに時を刻むので、出来事を起こす時点より後に、別の人物の出来事が既にあることがある。その場所か当事者に掛かる
そうした出来事(`age` で差し込むときは主役自身の後の出来事も)は、要約を添えて「この時点より後に既に決まっている出来事」として
記録を決める段にも小説に書き起こす段にも渡し、矛盾させない。`age` を渡したときは、直前の出来事はその時点より前に終わったものに限り、
その時点に別の出来事の最中にいる者は当事者から外す(主役なら選び直す)。
ルーチンで起こした出来事は `CommitEvent` を通らないので、ルーチンの頭でミームも棚卸しする(`meme.refresh`)。
前の回までに起こした出来事から、当事者が行き着いた考え方をミームとして抜き出す。

場所の出来事(`place_event`)は、毎日のルーチンの主役の代わりに場所・時刻・`key`(ジャンルや場面を一言で。「市場の喧嘩」「怪談」など)を決めて起こす。
それ以外は毎日のルーチンと同じ(頭でのミーム・種の棚卸し、種を引く、作品の本文を渡さない、後の出来事を渡す、小説に書き起こす)。
当事者の候補は、その時刻にその場所にいて(`character_place`)、別の出来事の最中でない、生きているサブキャラクター。
場所を名指しするので、場所の `active_random_generation` は見ない。`key` は候補・記録・小説のすべての段に場面の指定として渡し、
小説は当事者のうち指定が一番よく伝わる一人の視点で書く。`time` は `Stamp` か `"11579/03/02"` の形の文字列。
居合わせる者がいなければ何もせず None を返す(`ai/time_keeper/place_event_generator.py`)。

話の生成(`episode`)は、作者が決めた種(`key`)・時刻・登場人物(`character_ids`)から、作品(`story_id`)に話を一話足す。
`story_writer` と違い、書く位置(本文の入っている最後の話の次)も世界の断面も見ず、材料は呼び出し側が名指しする。
前の話(`previous_episode_ids`)は概要と文体の覚え書きで渡し(省けば作品の中で `time` より前の三話)、
登場人物ごとに、その時点の歳・人となり・口調・相関・直近の出来事(要約)を渡す。場所(`place_id`。省けば作品の立つ場所)の
直近の出来事と、その場所か登場人物に掛かる「この時点より後に既に決まっている出来事」も渡し、矛盾させない。
種から中間段でアイデアを引いて「関係する設定」として渡し、話に結ぶ(`episode_idea`)。
足した話は `key` / `start` / `title` / `text` / `viewpoint`(渡さなければ AI が選んだ視点人物)/ `place`(`place_id` を渡したときだけその名前)を持ち、
自動生成なので `synced` を立てる。Claude では本文だけ `story_writer` と同じモデルで書く。
`episode_id` を渡すと、話を足さずにその枠(同じ作品の、本文の無い話)へ書く。`key` / `time` / `viewpoint` は省けば枠のものを使い、
題は枠に題があればそれを残す。枠は前の話から外す。本文のある話・別の作品の話は書き換えずに止まる。
本文が得られなければ話を足さず(枠も変えず)に None を返す(`ai/time_keeper/episode_generator.py`)。

上の表の「作る」「確定する」入口を使えば、Claude も対話の中で人物・場所・出来事の
内容を決めて確定してよい。

## 作り方

置き場所は `<領域>/<動詞_対象>.py`。領域はいまのところ次の八つ。

- `randomizer/` — ランダム生成(作る／確定する)と、確定済みレコードの修正
- `story/` — 作品・話(`story`/`episode`)まわりの読み書き(材料を引く・本文を確定する)
- `sync/` — db と md の同期
- `world/` — 場所・人物・アイデア・出来事の一覧(読む専用)
- `meme/` — アイデア・oracle・人物の筋書き・出来事からのミームの抽出と、人物に持たせるミームの引き出し
- `idea/` — 中間段(下書きの語をアイデアと照らす・本文とアイデアを結ぶ)
- `review/` — ユーザの判断が要るものの一覧(読む専用)
- `fact_check/` — アイデア・oracle・ミームを AI に Dラボのナレッジとネット検索で検めさせ、妥当性と補足を書く(`ai/claude_code/fact_checker.py`)

- **「作る」と「確定する」を別ファイルに分ける。** 「作る」側(`create_random_*`)は
  db に一切触れず、素の辞書 / JSON を返すだけ。db を触るのは「確定する」側だけ
- 辞書 / JSON で受け渡しするのは、Bash 呼び出しをまたいでも(＝プロセスが
  切り替わっても)中身を運べるようにするため。SQLAlchemy のオブジェクトや
  session を返すと、次の呼び出しでは中身が失われる
- 実在レコードを指す欄(id)は、確定する側が呼び出し時に db に居るか確かめる
  (`check_exists`)。スキーマに無い欄が混ざっていたらそこで止める(`check_columns`)

各領域に共通する処理はクラスへ寄せ、その領域の入口の**上位**(`<領域>/_base.py`)
に置く。さらに四領域をまたいで共通する部分(db セッションを開いて渡す・
「確定する」系の実在確認とスキーマ列チェック等)は、一段上の
`ai/claude_code/interface/_base.py` に置く。`_rows.py` と同じく、先頭が `_` の
ファイルはそれ自体が claude の呼ぶ入口ではない。

```
Entrypoint(interface/_base.py)
├─ SessionEntrypoint            db セッションを開いて execute(session) へ渡す
│   ├─ CommitEntrypoint         「確定する」系の共通処理(parse/check_columns/check_exists)
│   │   ├─ randomizer.CommitDraft   → commit_*.py / update_*.py / delete_*.py / merge_idea.py
│   │   ├─ story.StoryCommit        → commit_*.py / update_story.py / delete_story.py / set_episode_synced.py
│   │   └─ idea.ResolveTerms / idea.LinkIdeas(候補を足す・結ぶので確定側)
│   ├─ world.WorldQuery          → list_*.py
│   ├─ world.SearchIdeas         (単独。あいまい検索)
│   ├─ review.ListPendingReviews (単独。読む専用)
│   ├─ story.StoryQuery          → list_*.py / read_*.py / start_story.py
│   └─ meme.DrawMemes            (単独。引くだけで db に書かない)
└─ randomizer.RandomDraft        db に触れない下書き作成 → create_random_*.py
```

(`sync/` の二つと `meme.extract_memes.ExtractMemes`・`fact_check.check_facts.CheckFacts` は、`execute(session)` の外で
db セッションを開き直したいので `Entrypoint` を直接継ぐ)

## 引き方は query 側にある

読む側の中身は `data_access_logic/query/` にある。

| モジュール                     | 何のため                                                     |
| ------------------------------ | ------------------------------------------------------------ |
| `common_query.py`              | 時刻の扱い・断面・顔ぶれ・場所の道筋                         |
| `character_simulation_query.py` | 人物を軸に周辺を読む(`read_surroundings`)                   |
| `dictionary_query.py`          | アイデア(辞書)の検索。名前・本文の部分一致、場所・時刻の範囲、自動生成の候補 |
| `story_createion_query.py`     | 場所に掛かる作品(`story`)の読み出し                          |
| `world_createion_query.py`     | 生きている人物、広さの整合、進行中の判定               |
| `event_seed_query.py`          | 出来事の種をまだ抜き出していない元(`event_seeded` が false) |
| `review_query.py`              | ユーザの判断が要るもの(本文に残った TODO・世界観へ反映していない話) |

ここのファイルはその薄い呼び出し面で、**SQL は組み立てない。**
引く条件は時刻とレコードの id だけで表す。足りない引き方が出てきたら
query 側に関数を足して、ここに入口を一つ被せる。
