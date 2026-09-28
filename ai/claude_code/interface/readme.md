claude が db を触るときに呼ぶ入口を置く場所。**操作前にこの readme を引く。**

各ファイルは**一つの呼び出しクラスだけ**を持つ。呼び出し側(claude)は、
そのクラスをインスタンス化して `run()` を呼ぶだけでよい
(CLI 引数のパースはしない。`if __name__ == "__main__"` も置かない)。

    from ai.claude_code.interface.world.list_places import ListPlaces
    ListPlaces(kind="村").run()

db の触り方(入口越し・読み取り)は CLAUDE.md の「db への接続」を見る。ユーザが見て直す窓口は `gui/`。
ここの入口は GUI の API(`POST /api/interface/<領域>.<ファイル>.<クラス>`)からも同じ引数で呼べる(`gui/readme.md`)。

## 依頼内容 → 呼ぶコード

`ai.claude_code.interface.` を頭に付けて import する。

| 依頼内容(言い回しの例)           | 呼ぶコード                                                                 |
| ---------------------------------- | -------------------------------------------------------------------------- |
| 「どんな場所がある?」「村の一覧」   | `world.list_places.ListPlaces(kind=None)`                                    |
| 「この場所の近くには何がある?」     | `world.list_neighbors.ListNeighbors(place_id, kind=None, limit=None)`。同じ星の他の場所の方角・距離・高低差を近い順に返す |
| 「人物の一覧」「誰がいる?」         | `world.list_characters.ListCharacters()`                                     |
| 「人物同士の関係は?」               | `world.list_character_relations.ListCharacterRelations(character_id=None)`   |
| 「出来事の一覧」                     | `world.list_events.ListEvents()`(全件)。絞るなら `story.read_events.ReadEvents(time=…)` か、`ReadEvents(place_id=…)` / `ReadEvents(character_id=…)` / `ReadEvents(event_id=…)`(どの表の id かを名前で渡す) |
| 「このアイデアは何?」「アイデアを調べて」 | `world.search_ideas.SearchIdeas(keywords, place_id=None, limit=None, time=None)`。名前・本文(基本の本文と追記の両方)の部分一致のあいまい検索。`keywords` は語一つか、`{"keyword", "variants"}`(言い換え)のリスト。当たり方の強い順に返す。自動生成の候補も返す。`place_id` は現在地から最上位までの場所に、`time` はその時刻に効く(`start` <= time < `end`)アイデアに絞る。`called` はその場所・時刻での作中の呼び名。`text` は `time` の時点に効く追記(下の「アイデアの追記」)まで積み重ねた本文 |
| 「この下書きに関わる設定は?」(中間段を自分で回す) | `idea.resolve_terms.ResolveTerms(terms, place_id=None, time=None)`。下書きから洗い出した語(`{"keyword", "variants", "description", "kind", "start", "end"}`)をアイデアと照らし、当たったものと上位・下位を返す。当たらなかった語は候補として足す(下の「中間段」)。候補の効く期間は語の `start` / `end`。`start` は `time` と下書きの中身からある程度はっきり言えるときだけ付け(言えなければ省いて None)、`end` は分かるときだけ付ける。`time` は出来事の時刻。`time` を渡すと `start` が空(時期が未定)のアイデアは `ideas` に入れない。呼び名に当たったら本質のアイデアにそろえ、作中の呼び名を `called` に付ける |
| 「この本文が踏まえたアイデアを結んで」 | `idea.link_ideas.LinkIdeas(idea_ids, event_id=None, episode_id=None, character_id=None)`。三つのうち一つだけ渡す |
| 「この候補をあのアイデアにまとめて」 | `randomizer.merge_idea.MergeIdea(source_id, target_id)`。結んだ本文と source の認識(呼び名)を付け替えてから source を消す |
| 「判断待ちの一覧」「週次レビュー」   | `review.list_pending_reviews.ListPendingReviews()`。候補のアイデア・候補のミーム・未同期の話・本文に残った TODO。Todoist へ載せる手順はスキル `weekly-review` |
| 「場所を足して」                     | `randomizer.create_random_place.CreateRandomPlace()` で下書き → 内容を決めて `randomizer.commit_place.CommitPlace(place)` |
| 「人物を足して」                     | `randomizer.create_random_character.CreateRandomCharacter()` → `randomizer.commit_character.CommitCharacter(character)`。持たせるミームは `meme.draw_memes.DrawMemes(person=True)` で引き、`text` の `# meme` 節と `# 行動原理` 節に書く(下の「人物が持つミーム」)。`# 来歴` 節には節目を歳付きで書く(下の「人物の来歴」) |
| 「この場所にランダムな人物を何人か作って」「全国家に人物を生成」 | `randomizer.generate_characters.GenerateCharacters(place_ids, time, count=(2, 4), person=True, seed=None)`。場所ごとに `count` の範囲の人数を、時の流れの中で生む人物と同じ自動生成(`_generate_one`。性格・ミーム・来歴・名づけまで AI が決める)で作り、`time` の時点で生まれた歳にする。一人ごとに commit する。作品の無い場所が混ざっていれば作る前に止まる。`person=False` で人物以外の対象を作る。`confirmed=未確認` で足す(下の「出来事・人物の承認フラグ」) |
| 「出来事を足して」                   | `randomizer.create_random_event.CreateRandomEvent()` → `randomizer.commit_event.CommitEvent(event)` |
| 「この下書きから人物を AI に作らせて」「GUI の AI で作成/補完(人物)」 | `randomizer.generate_character.GenerateCharacter(character={...}, time=None, seed=None)`。欄の値(全部空でもよい)を核に、時の流れの中で生む人物と同じ自動生成(`_generate_one`)で全欄を組み立て直して足す。名前・説明は核として渡し、性別・体格・口調・性格・種別・生年・没年・`main_character` は決まった値にする。`time`(現在の時刻)を省けば世界の最新の出来事の時刻。`character` に `id` を渡せば(GUI の詳細画面)、その人物の本文(`text`)が空のときに限り、決まっている名前・属性・出自を核に本文だけを書いて埋める(他の欄は変えない)。新しく作るときは `confirmed=未確認` で足す |
| 「この下書きから出来事を AI に作らせて」「GUI の AI で作成/補完(出来事)」 | `randomizer.generate_event.GenerateEvent(event={...}, seed=None, shared_style_extra="", style_extra="")`。場所の出来事(`place_event`)と同じ生成を、名前・記録を場面の指定に、時刻・場所・当事者を決まった値として回す。時刻を省けば世界の最新、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。`event` に `id` を渡せば(GUI の詳細画面)、その出来事の本文(`text`)が空のときに限り、記録・当事者・関連する設定から小説の本文だけを書いて埋める(他の欄は変えない)。新しく作るときは `confirmed=未確認` で足す |
| 「この人物の出自・居場所を足して」   | `randomizer.commit_character_place.CommitCharacterPlace(place)`              |
| 「この二人の相関を足して」           | `randomizer.commit_character_relation.CommitCharacterRelation(relation)`     |
| 「アイデアを足して」                 | `randomizer.commit_idea.CommitIdea(idea, fact_check=True)`。効く場所は `location_id`(その場所と配下で効く)、効く期間は `start` / `end`(出来事の時刻と比べる。空なら限らない)。`parent_idea_id` を渡さなければ、`kind` の分類アイデア(下の「アイデアの分類」)を `location_id` から自動で探して親にする(無ければ作る)。時代ごとの追記は `notes`(下の「アイデアの追記」)、場所・時代ごとの作中の呼び名は `recognitions`(下の「アイデアの認識(呼び名)」)。確定したあと、AI が Dラボのナレッジとネット検索でアイデアの妥当性・補足を検め、`fact_check` 欄(md の `# fact_check` 節)へ書く。続けて本文と検証結果のそれぞれからミームを抜き出し(`memes_added`)、足したミームも検める。`fact_check=False` で検めずに本文からだけ抜き出す |
| 「作中での呼び名を足して」「この場所・時代では〇〇と呼ぶ」 | `randomizer.commit_idea.CommitIdea(idea)` / `randomizer.update_idea.UpdateIdea(idea)` に `recognitions`(下の「アイデアの認識(呼び名)」)を付けて足す。呼び名を使う場所・時代は各行の `location_id` / `start` / `end`(空の列はどこでも・いつでも) |
| 「アイデア・oracle・ミームを検めて」「妥当性を調べて」 | `fact_check.check_facts.CheckFacts(table, ids=None, limit=None)`。`table` は `"idea"` / `"oracle"` / `"meme"`。AI が Dラボのナレッジ(優先)とネット検索で妥当性と補足を書き、`fact_check` 欄へ入れる。`ids` を省くと `fact_check` が空のものすべて(`limit` で件数を絞る)、渡すと検め済みでも検め直す。アイデア・oracle は検めたあと本文と検証結果からミームを抜き出し直し、足したミームも検める。`{"checked", "memes_added"}` を返す |
| 「場所を直して」                     | `randomizer.update_place.UpdatePlace(place)`                                 |
| 「この人物の〇歳からの名字・背丈・口調・性格を決めて」「結婚して名字が変わる」 | `randomizer.update_character.UpdateCharacter({"id": …, "parameters": [...]})`。期間ごとの行の配列をまるごと渡す(下の「期間ごとのパラメータ」)。今の配列は `ReadCharacter` の `parameters` で読める |
| 「この人物の説明の移り変わりを足して」「〇年からの立場を記録して」 | `randomizer.update_character.UpdateCharacter({"id": …, "histories": [...]})`。期間ごとの行の配列をまるごと渡す(下の「期間ごとの説明の変化(character_history)」) |
| 「人物を直して」                     | `randomizer.update_character.UpdateCharacter(character)`。名字・体格・口調・性格は `parameters` に、説明の期間ごとの変化は `histories` に入れる(渡さなければ触らない)。出自・居場所は `randomizer.update_character_place.UpdateCharacterPlace(place)`、相関は `randomizer.update_character_relation.UpdateCharacterRelation(relation)` |
| 「場所を消して」                     | `randomizer.delete_place.DeletePlace(place_id)`                              |
| 「出来事を直して」                   | `randomizer.update_event.UpdateEvent(event)`。`id` 必須、渡した欄だけ直す。当事者は変えない。直したあと要約(`event_summary`)を作り直す |
| 「出来事を消して」「出来事を作り直して」 | `randomizer.delete_event.DeleteEvent(event_id)`。子の出来事が残っていれば止まる。当事者・アイデアとの中間テーブルの行と要約も消す。出来事で人物の `text` に積み足した一文と、足したアイデアの候補は残るので、要らなければ `UpdateCharacter` / `DeleteIdea` で別に戻す |
| 「アイデアを直して」                 | `randomizer.update_idea.UpdateIdea(idea)`。`id` 必須、渡した欄だけ直す。`notes` / `recognitions` を渡すとそれぞれ配列をまるごと置き換える(下の「アイデアの追記」「アイデアの認識(呼び名)」) |
| 「アイデアを消して」                 | `randomizer.delete_idea.DeleteIdea(idea_id)`。下位のアイデアが残っていれば止まる。結んだ本文との中間テーブルの行、認識(呼び名)・追記の行も消す |
| 「覚え書きを足して」「oracle に書いて」 | `randomizer.commit_oracle.CommitOracle(oracle, fact_check=True)`。`text` 必須。題は `title`。確定したあとは `CommitIdea` と同じく、検めて(`fact_check`)、本文と検証結果のそれぞれからミームを抜き出し(`memes_added`)、足したミームも検める |
| 「覚え書きを直して」                 | `randomizer.update_oracle.UpdateOracle(oracle)`。`id` 必須、渡した欄だけ直す |
| 「ミームを足して」「この考え方をミームに入れて」 | `randomizer.commit_meme.CommitMeme(meme)`。`text` 必須。`category` は 信条/欲求/境遇/集団/理 のいずれか(空でもよい。次の抽出で AI が振る)。ユーザが書いたものなので `confirmed` を渡さなければ 承認 で入れ、置き場所は分類のディレクトリ |
| 「ミームを直して」「ミームの分類を直して」 | `randomizer.update_meme.UpdateMeme(meme)`。`id` 必須、渡した欄だけ直す。`category` は 信条/欲求/境遇/集団/理 のいずれか |
| 「ミームを消して」                   | `randomizer.delete_meme.DeleteMeme(meme_id)`                                 |
| 「出来事の種を直して」               | `randomizer.update_event_seed.UpdateEventSeed(seed)`。`id` 必須、渡した欄だけ直す。語の置き換えなどは db を読んで id を拾ってから呼ぶ |
| 「ミームを抜き出して」               | `meme.extract_memes.ExtractMemes()`。アイデア・oracle(著者の覚え書き)の本文と検証結果(`fact_check`。別々の元として渡す)・人物の筋書き(`# plot`)・出来事の本文から抜き出し、分類を振って `confirmed=未確認` で `meme` テーブルへ足す。既にあるミームと同じ考え方の言い換えは足さない。最後に、分類の空いたミーム(手で足したものなど)に分類を振る。足したミームは AI が Dラボのナレッジとネット検索で検め、`fact_check` 欄へ書く(`ExtractMemes(fact_check=False)` で飛ばす)。足した件数を返す。抜き出しただけでは `DrawMemes` に出ず、ユーザが GUI で承認するまで、人物へ引く・書き込む文脈には使われない(「判断待ちの一覧」に候補として出る) |
| 「ミームを引いて」                   | `meme.draw_memes.DrawMemes(person=True, seed=None)`。ユーザが確かめた(`confirmed=承認`)ミームだけから、分類ごとに 0〜2 件引き、それぞれに古今表裏を割り振って返す。db には書かない |
| 「ミームと要約の取りこぼしをまとめて作って」 | `meme.refresh_generated_content.RefreshGeneratedContent()`。`ExtractMemes` に加えて、まだ要約の無い出来事・話もすべて見て `event_summary` / `episode_summary` を作る。`CommitEvent` / `CommitStory` / `CommitEpisode` は確定した一件だけを見るので、GUI から直した分などの取りこぼしを拾うのはこちら |
| 「作品の一覧」                       | `story.list_stories.ListStories()`                                           |
| 「話を書き始める」「次の話を書く」   | `story.start_story.StartStory(story_id)`。同期確認・見出し・直前の話・断面・顔ぶれを一度に出す |
| 「前の話を読ませて」                 | `story.read_episodes.ReadEpisodes(story_id, count=10, before=None, text=True)`。`before` は時刻で、start がそれより前の話に絞る |
| 「その時点の顔ぶれは?」             | `story.read_cast.ReadCast(story_id, time=None)`                              |
| 「その場所・その時点の様子は?」     | `story.read_brief.ReadBrief(place_id, time)`                                 |
| 「この人物の周りで何が起きている?」 | `story.read_surroundings.ReadSurroundings(character_id, time)`               |
| 「この人物を本文用にそろえて」       | `story.read_character.ReadCharacter(character_id, time=None)`。体格・口調・性格は `time` の時点の値を上の段に出す(`time` を省くと期間を限らない値だけ)。期間ごとの行は `parameters`。外見・口調の推敲はこれで足り、`character.text` の全文(来歴・meme 込み)まで読み直さなくてよい(来歴・行動原理を確かめたいときだけ `text` を読む) |
| 「作品を作る」「筋書きを足して」     | `story.commit_story.CommitStory(story)`。筋書きは作品の `text` に書く        |
| 「作品を直して」「筋書きを直して」   | `story.update_story.UpdateStory(story)`                                      |
| 「作品を消して」                     | `story.delete_story.DeleteStory(story_id)`。話が残っていれば止まる           |
| 「この下書きから話の枠を AI に決めさせて」「GUI の AI で枠を作る」 | `story.generate_frame.GenerateFrame(frame={"story_id": …, "viewpoint_character_id": …, "place_id": …, "character_ids": […], …}, character_ids=None, previous_episode_ids=None)`。題・種(`## 場面` / `## 狙い` の形)・時刻を下書きを核に AI が決めて、本文の無い話を足す(`id` を渡せばその本文の無い枠を決め直す)。時刻は下書きにあればそれ、無ければ直前の話の後から AI が選ぶ。視点(`viewpoint_character_id`。Character への FK)・場所(`place_id`。Location への FK)は AI には決めさせず、下書きにあればその id をそのまま使う(無ければ NULL のまま)。登場人物は `character_ids`(省けば下書きの `character_ids`、それも無ければ枠の `episode_character`)で、足した枠の `episode_character` にも残す |
| 「この下書きから一話ぶん AI に書かせて」「GUI の AI で本文まで書く」 | `story.generate_episode.GenerateEpisode(episode={"story_id": …, "viewpoint_character_id": …, "place_id": …, "character_ids": […], …}, character_ids=None, previous_episode_ids=None, model=None, effort=None, shared_style_extra="", style_extra="")`。種と時刻が揃っていれば常駐ループの `write_episode` と同じ生成で本文を書き、どちらかが空なら先に `GenerateFrame` と同じ生成で枠を決める。`id` を渡せばその本文の無い枠へ書く。登場人物は `character_ids`(GUI の生成パネルで選んだ人物)、省けば下書きの `character_ids`(話の `episode_character` と同じ欄)、それも無ければ枠の `episode_character` で、空なら AI を呼ぶ前に止まる(時刻・場所から人物を拾う既定は無い)。視点・場所は下書きの `viewpoint_character_id` / `place_id`(どちらも Episode の列。省けば NULL のまま、既存の枠を書くときは枠のものを使う)。`model` / `effort` は本文を書く Claude の呼び出しにだけ効く選択肢で、db には残らない(`episode.model` / `episode.effort` 列は廃止した)。使う登場人物は AI 呼び出しの前に、その話の登場人物リレーション(`episode_character`)として保存される |
| 「この話を推敲して」「初登場キャラの描写を厚くして」 | `story.revise_episode.ReviseEpisode(episode={"id": …, "character_ids": […]}, instruction="…", character_ids=None, previous_episode_ids=None, model=None, effort=None, shared_style_extra="", style_extra="")`。すでに本文のある話を、`instruction`(直す指示。必須)に沿って AI に書き直させる。筋は変えず指示にある観点だけを直す。登場人物(この話に出る人物。初登場・既出とも)は `character_ids`、省けば下書きの `character_ids`、それも無ければこの話の `episode_character` で、空なら止まる。前の話の概要に出ていない人物は、AI が初登場と判断して外見・性格の描写を厚くする。場所はこの話自身の `place_id` を使う。本文が無い話は先に `GenerateEpisode` で書く。`model` / `effort` は本文を書く Claude の呼び出しにだけ効く選択肢で、db には残らない。使った登場人物は、この話の `episode_character` としても保存される(既存の関連を全置換)。
`instruction` はキーテキスト(`episode.key`)の末尾に「## 推敲」の節として自動で積まれる(二回目以降は見出しを重ねず箇条書きを足す) |
| 「本文を確定する」「話の種を入れる」 | `story.commit_episode.CommitEpisode(episode)`。`id` を渡せばその話を直し(渡した欄だけ)、省けば `story_id` の作品に新しい話を足す。`key`(種)か `text`(本文)のどちらかがあればよい。`text` は `ai/instructions/style.py` の `layout_novel_text` で改行を整えてから入れる(地の文は一文一行、「◇」の行は空行二つ)。話に番号は無く、作品の中では `start` の順に並ぶ(`start` の無い話は後ろに id 順)。あいだに話を足すときは、前後の話のあいだの `start` を付ける |
| 「未同期の話は残ってる?」           | `story.list_unsynced_episodes.ListUnsyncedEpisodes(story_id=None)`           |
| 「世界観へ反映済みにする」           | `story.set_episode_synced.SetEpisodeSynced(episode_id, synced=True)`   |
| 「世界を進めて」「ループを回して」   | 入口ではなく常駐ループ。「常駐ループ」を見る                                  |
| 「毎日のルーチン」「サブキャラの次の出来事を起こして」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `daily_event`。主役を決めるなら `character_id` を渡す。「〇〇の17歳の出来事」のように歳を決めるなら `age` も渡す(直前の出来事の後ではなく、その歳のうちに差し込む) |
| 「この場所・この時の出来事を起こして」「ヴァレンツァで11579/03/02に〇〇な場面」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `place_event`。場所 id・時刻・`key`(ジャンルや場面を一言で)を渡す。当事者はその時刻にそこにいるサブキャラクターから選ぶ |
| 「この種で話を書いて」「〇〇と△△が出る話を 11579/03/02 で」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `write_episode`。作品 id・`key`(話の種)・時刻・登場人物の id のリストを渡す。前の話を名指しするなら `previous_episode_ids`(省けば作品の中でその時刻より前の三話)。場所・視点を決めるなら `place_id` / `viewpoint_character_id`。題・時刻だけ決めた本文の無い話(枠)へ書くなら `episode_id`(種・時刻・視点・題は省けば枠のもの) |
| 「この枠に本文を書いて」「話 id=40 の本文を生成して」 | 入口ではなく常駐ループ側。「常駐ループ」の表の `fill_episode`。枠の話 id と登場人物の id のリストを渡す。種・時刻・視点・場所は枠のものを使う。本文のモデルを変えるなら `model` / `effort`(省けば fable の high) |

**まだ入口が無いもの**(頼まれたら作ってから行う): 人物の削除。

筋書きのテーブルは無い。場所に掛かる筋書きは作品(`story`)の
`text` に、人物に掛かる筋書きはその人物の `text` の `# plot` の節に書く。

**期間ごとのパラメータ**: 人物の名字(`family_name`)・体格(`sex` `height` `build`)・口調(`first_person` `second_person` `third_person` `tone` `dialect`)・
性格(12 軸。無/低/並/高/必)は、`character_parameter` テーブルに期間ごとの行で持つ。入口では人物の
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
- 時刻を渡さずに引くと、一番限る端が少ない(一番土台になる)行だけを重ねる
- 人物の誕生・死亡(`start` / `end`)も専用の列を持たず、この `parameters` の一番早く始まる行の `start`・
  一番後に始まる行の `end` で表す。`CommitCharacter` / `UpdateCharacter` へは今までどおり人物の欄として
  トップレベルの `start` / `end` を渡してよく(誕生だけなら `start` だけでよい)、入口が該当する行へ書き込む。
  読み出し(`ReadCharacter` など)も人物の `start` / `end` としてそのまま出る
- 一番後に始まる行の `end` は死亡を兼ねるので、死んでいない人物・対象では空にする。育ちなどの区切りで
  「この段階の値はここまで」を表したいときも、まだ次の段階の行を足していないなら、この行の `end` は
  空のままにする(埋めると死亡と区別が付かなくなる)。次の段階が決まったら、新しい行を足す側で表す
- 生成(毎日のルーチン・出来事の進行)は、出来事の時刻の値を使う。人物の自動生成・`CreateRandomCharacter` は期間を限らない一行だけを作る
- `CommitCharacter` / `UpdateCharacter` は `parameters` を受け取る。`UpdateCharacter` に渡すと配列をまるごと置き換える
- `name` は名字を含めない名だけを持つ。名字は `family_name` に分け、結婚・養子・家の取り立てなどで変わるなら、
  変わった時点からの行を足す。名字を持たない身分なら空。`CreateRandomCharacter` の下書きでは空なので、
  出自・身分・土地柄から決めて入れる(時の流れの中で生む人物は、名づけのときに AI が決める)

**期間ごとの説明の変化(character_history)**: 人物の説明の変化は、`character.text` 自体を書き換えず、
`character_history` テーブルに期間ごとの行(`start` / `end` / `description`)で積む。入口では人物の
`histories` に配列で並ぶ(id と character_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。
下の「アイデアの認識(呼び名)」と同じ扱いの子テーブルで、GUI の見た目もそちらに揃えている。

```json
"histories": [
  {"start": null, "end": "11600", "description": "村の鍛冶屋の徒弟として働いていた"},
  {"start": "11600", "end": null, "description": "師の死後、鍛冶屋を継いで営んでいる"}
]
```

- `start` / `end` が空なら、その端は限らない。両方空の行は全期間に効く。`end` の時刻からは効かない
- `description` は必須。その期間での人物の説明
- `CommitCharacter` / `UpdateCharacter` は `histories` を受け取る。`UpdateCharacter` に渡すと配列をまるごと置き換える
- 下の「人物の来歴」で説明する `text` の `# 来歴` 節(節目の箇条書き)とは別物。今のところ両者を自動で同期する仕組みは無い

**アイデアの追記**: アイデアの基本の本文(`text`)は書き換えず、時代が進むにつれて分かった・変わった情報は
`idea_note` テーブルに期間ごとの行(`start` / `end` / `text`)で積む。入口ではアイデアの `notes` に配列で並ぶ
(id と idea_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。

```json
"notes": [
  {"start": "11600", "end": null, "text": "この年、量産が始まった"},
  {"start": "11650", "end": "11700", "text": "一時、材料の枯渇で作れなくなった"}
]
```

- `start` / `end` が空なら、その端は限らない。ある時刻の本文は、基本の本文に、その時刻に効く追記
  (`start` <= 時刻 < `end`)を `start` の古い順に積み重ねて作る。効く追記が無ければ(そもそも一つも
  無い場合も含め)基本の本文がそのまま全て
- `CommitIdea` / `UpdateIdea` は `notes` を受け取る。`UpdateIdea` に渡すと配列をまるごと置き換える
- `SearchIdeas` の名前・本文検索、`idea_search`(あいまい検索の当たり方の判定)、清書に渡す
  「関係する設定」(`idea_context.prompt_section`)は、いずれもこの積み重ねた本文を使う

**アイデアの認識(呼び名)**: アイデアの作中での呼び名(本質の `name` とは別に、この場所・この時代ではこう呼ぶ、
という言い方)は、`idea_recognition` テーブルに場所・時代ごとの行(`location_id` / `start` / `end` / `name` / `detail`)
で積む。入口ではアイデアの `recognitions` に配列で並ぶ(id と idea_id は出さない。行は配列の並びで決まり、
並びを変えなければ id も変わらない)。

```json
"recognitions": [
  {"location_id": 12, "start": null, "end": "11700", "name": "魔力", "detail": "住人は魔法の力だと思っている"},
  {"location_id": null, "start": null, "end": null, "name": "力", "detail": null}
]
```

- `location_id` は効く場所(その場所と配下で効く)、`start` / `end` は効く期間。どちらも空ならどこでも・いつでも効く
- `name` は必須。その場所・時代でアイデアをこう呼ぶ、という作中の呼び名
- `detail` は呼び名についての注釈(作中でどう受け止められているか)。無くてもよい
- `CommitIdea` / `UpdateIdea` は `recognitions` を受け取る。`UpdateIdea` に渡すと配列をまるごと置き換える
- `SearchIdeas` の名前・本文検索、`idea_search`、`idea_context`(中間段)、清書に渡す「関係する設定」
  (`idea_context.prompt_section`)は、いずれもアイデアの `recognitions` を見て、当てはまる場所・時代の
  認識があればその `name` で呼び、`detail` を本質の本文の前に添える。当てはまる認識が無ければ本質の `name` をそのまま使う
- ある場所・時代の認識(呼び名)がある行は、清書のプロンプト(`ai/instructions/idea_context.py`)で
  「その場所・時代の人物はこの名前を認識しているもの」として扱われ、本文ではその名で呼ぶ
- `MergeIdea` は `source_id` の `recognitions` を `target_id` へ付け替えてから `source_id` を消す。
  `DeleteIdea` は下位のアイデアが残っていなければそのまま消し、`recognitions` も一緒に消える

**アイデアの分類(親の自動探索)**: `parent_idea_id`(上位のアイデア)は、`kind` ごとに一つ、その kind を
まとめる「分類」のアイデア(`name` が `kind` と同じ。例: `name="組織" kind="組織"`)を親にしてぶら下げる。
`CommitIdea` に `parent_idea_id` を渡さなければ(中間段(下の「中間段」)が候補を足すときも同様)、
`ai/time_keeper/idea_context.py` の `find_or_create_classification` が `location_id` の場所チェーンを
根まで遡り、対応するアイデア(たいていは「星」のアイデア)が見つかった一番深いところを探して、その配下で
`kind` の分類を探す。あれば再利用し、無ければ `name=kind` の分類を新しく作って親にする(`confirmed=承認`)。
場所チェーンのどこにも対応するアイデアが無ければ親を決めようがないので、`parent_idea_id` は空のまま
(明示的に渡した `parent_idea_id` はそのまま尊重し、自動探索はしない。分類自体を足すとき(`name == kind`)も、
自分自身の親を探しに行かない)。

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
- ユーザが確かめた(`confirmed=承認`)ミームだけを引く。抜き出したばかりの `confirmed=未確認` のミームと、退けた `非承認` のミームは、
  週次レビューで確かめられるまで、毎日のルーチン・場所の出来事・人物生成のどれでも文脈に取り入れられない
- 時の流れの中で生む人物(`ai/time_keeper/random_character_generator.py`)は、この引き方と整理を自動で行う

## 出来事・人物の承認フラグ

`event` / `character` も `confirmed`(未確認/承認/非承認)を持つ。列の既定値は 承認(GUI から手で足す・
`CommitEvent` / `CommitCharacter` で確定するときは渡さなければ 承認)だが、ランダム生成(常駐ループの毎日の
ルーチン・場所の出来事・自然死・`GenerateCharacter(s)` / `GenerateEvent` が使う自動生成)は明示的に
`confirmed=未確認` で足す。ユーザが GUI のレビュー画面(`reviewable=True`)で確かめて 承認 にするまで:

- `write_episode` / `fill_episode`(`GenerateEpisode` / `GenerateFrame` も同じ)は、渡された `character_ids`
  (省いたときは話の `episode_character`)に未確認・非承認の人物が混ざっていると止まる
- 話に渡す材料(場所の直近の出来事・登場人物それぞれの直近の出来事)も、未確認・非承認の出来事は使わない
- `ReadCast` / `ReadBrief` の顔ぶれ、`ReadSurroundings` の周りの人物・出来事にも、未確認・非承認は出てこない

(「この時点より後に既に決まっている出来事」は、まだ確かめていない出来事でも矛盾を避けるために渡す。
毎日のルーチン・場所の出来事どうしの候補選び・当事者選びも、承認済みに絞らない)

## 中間段(下書き → 語の洗い出し → 清書)

本文を書く生成は、下書き(一段目)と清書(二段目)のあいだに、アイデアと照らす中間段を挟む
(`ai/time_keeper/idea_context.py`)。

1. 下書きから、設定資料と照らす語とその言い換えを AI に挙げさせる(`idea_search.keywords_of`)。
   出来事の時刻と下書きの中身から、語ごとの `start` / `end` も決めさせる。ある程度はっきりした `start` が言えない語は null、`end` は分かる語だけ
2. 語と言い換えで、アイデアの名前・本文(場所・時代ごとの作中の呼び名 `idea_recognition` の `name` / `detail` も含む)を
   部分一致で引く(`idea_search.search`)。その場所・時刻で効くアイデアだけ。
   場所は、アイデアの `location_id`(または当たった `idea_recognition` の `location_id`)が現在地から最上位までの場所のどれかに当たるもの。
   時刻は、出来事の時刻が `start` 以上 `end` 未満のもの(`end` が空なら限らない)。
   `start` が空のアイデアは時期が未定で、その時刻にもうあるかが分からないので、語が当たっても清書に渡さない(候補も足さない)。
   当たったアイデアに上位・下位のアイデアを足して、清書に「関係する設定」として渡す
3. どのアイデアにも当たらなかった語は、AI が決めた種別(`kind`)と `confirmed=未確認` で足す。
   場所は世界線、`start` / `end` は 1. で決めたもの(null ならそのまま空。時期が未定の候補になる)。親(`parent_idea_id`)は
   上の「アイデアの分類(親の自動探索)」の通り自動で決める。候補はミームの抜き出しには他のアイデアと同じく出るが、
   `confirmed` が 承認 になるまで検索・断面・清書には出ない(`SearchIdeas` だけは確かめる前の候補も探せる)。
   確かめたら `confirmed` を 承認 に、設定ではないと退けたら 非承認 にする(GUI のレビュー画面 `gui/` で行う)。非承認の語は候補に戻さない
4. 下書きが当たったアイデアと候補を、清書したレコードに中間テーブル(`event_idea` / `episode_idea` /
   `character_idea`)で結ぶ

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
- 話は `episode` テーブルに一話一行で持つ。枠(`key`。作者が入れる種、AI 生成前)と
  本文(AI か作者が書く、投稿する本文。`text`)を同じ行に持ち、時期・場所・視点は
  `start` / `end` / `place_id`(Location への FK)/ `viewpoint_character_id`(Character への FK)に入る。
  登場人物は `episode_character`(中間テーブル、多対多)で持つ。字数(`letters`)は本文から数える。
  書いたモデル・effort は db に残さない(選択肢はその場の Claude 呼び出しにだけ効く)
- 本文に字数の指定は無い(`ai/instructions/style.py` の `EPISODE_STYLE_BASE`)。種(key)と、渡された作品・登場人物・場所・
  直前の話・関係する設定などの周辺データを踏まえ、具体的な描写・会話・人物の動きまで詳しく書き起こす。
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
- 星ごとの地図と人物相関図は GUI の画面 `/maps`・`/relations` で描く(星ごとの svg は `/api/maps/{id}.svg`)
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
| 種・時刻・登場人物を決めて、作品に話を一話足す(`episode_id` で既存の枠へ書く) | `local_ai_time_keeper.write_episode(story_id, key, time, character_ids, previous_episode_ids=None, episode_id=None)` | `claude_code_time_keeper.claude_write_episode_main(story_id, key, time, character_ids, previous_episode_ids=None, episode_id=None, model=None, effort=None)` |
| 話の枠(種・時刻の入った本文の無い話)に、本文だけを書く | `local_ai_time_keeper.fill_episode(episode_id, character_ids, previous_episode_ids=None)` | `claude_code_time_keeper.claude_fill_episode_main(episode_id, character_ids, previous_episode_ids=None, model=None, effort=None)` |

(`ai.local_ai.` / `ai.claude_code.` を頭に付ける)

上の四つ(`daily_event` / `place_event` / `write_episode` / `fill_episode`。ローカル AI・Claude Code とも)は
`shared_style_extra` / `style_extra` も渡せる。世界の舞台設定や、既存の話から抽出した文体の癖のような
「ユーザーの好み」は `core` には定数で持たず(`ai/instructions/style.py` の `style_instruction()` を見る)、
呼び出し側(世界リポジトリ側。例えば `instructions/style.py`)がこの二引数で渡す。省けば空でよく、
その場合は `core` だけの汎用の文体になる。

毎日のルーチンは、人物ごとに生まれてから 5〜20 年後を起点に自分の時を刻む。作品の時期には合わせず、
作品の本文(筋書き)も渡さない。出来事の候補は、出来事の種(`event_seed` テーブル)から
ランダムに引いた種か、直前の出来事からの連想で立てる。種は作品の本文・話の種(`key`、無ければ本文)・
人物の `# plot` の節・出来事の本文から、時代・場所・固有名詞を抜いて抜き出したもの。ルーチンの頭で、
`event_seeded` が false の元だけから抜き出して true にする(`ai/time_keeper/event_seed.py`)。
抜き出しは元ごとに一度だけ。本文を書き直して抜き出し直したいときは、その行の `event_seeded` を false に戻す。
抜き出すときは似た種があるかを見ない。棚卸し前(`consolidated` が false)の種が 50 件たまったら、ルーチンの頭で
AI に棚卸し済みの種と見比べさせ、同じ出来事の言い換えだけをまとめる(`event_seed.consolidate`)。
人物ごとに時を刻むので、出来事を起こす時点より後に、別の人物の出来事が既にあることがある。その場所か当事者に掛かる
そうした出来事(`age` で差し込むときは主役自身の後の出来事も)は、要約を添えて「この時点より後に既に決まっている出来事」として
記録を決める段にも小説に書き起こす段にも渡し、矛盾させない。`age` を渡したときは、直前の出来事はその時点より前に終わったものに限り、
その時点に別の出来事の最中にいる者は当事者から外す(主役なら選び直す)。
ルーチンで起こした出来事は `CommitEvent` を通らないので、`confirmed=未確認` で足し、ルーチンの頭でミームも棚卸しする
(`meme.refresh`)。前の回までに起こした出来事から、当事者が行き着いた考え方をミームとして抜き出す。

場所の出来事(`place_event`)は、毎日のルーチンの主役の代わりに場所・時刻・`key`(ジャンルや場面を一言で。「市場の喧嘩」「怪談」など)を決めて起こす。
それ以外は毎日のルーチンと同じ(頭でのミーム・種の棚卸し、種を引く、作品の本文を渡さない、後の出来事を渡す、小説に書き起こす)。
当事者の候補は、その時刻にその場所にいて(`character_place`)、別の出来事の最中でない、生きているサブキャラクター。
場所を名指しするので、場所の `active_random_generation` は見ない。`key` は候補・記録・小説のすべての段に場面の指定として渡し、
小説は当事者のうち指定が一番よく伝わる一人の視点で書く。`time` は `Stamp` か `"11579/03/02"` の形の文字列。
居合わせる者がいなければ何もせず None を返す(`ai/time_keeper/place_event_generator.py`)。

話の生成(`write_episode`)は、作者が決めた種(`key`)・時刻・登場人物(`character_ids`)から、作品(`story_id`)に話を一話足す。
話に渡す登場人物は、話と人物のリレーション(`episode_character`)だけ。`character_ids` を渡せばそれでリレーションを置き換え、
枠へ書く(`episode_id` / `fill_episode` / `revise_episode`)ときに `None` を渡せば枠の `episode_character` を使う。
時刻・場所から人物を拾う既定(その時刻に生きているメインキャラクター・その場所に住む人物)は持たない。
`story_writer` と違い、書く位置(本文の入っている最後の話の次)も世界の断面も見ず、材料は呼び出し側が名指しする。
前の話(`previous_episode_ids`)は概要と文体の覚え書きで渡し(省けば作品の中で `time` より前の三話)、
登場人物ごとに、その時点の歳・人となり・口調・相関・直近の出来事(要約)を渡す。場所(`place_id`。省けば作品の立つ場所)の
直近の出来事と、その場所か登場人物に掛かる「この時点より後に既に決まっている出来事」も渡し、矛盾させない。
種から中間段でアイデアを引いて「関係する設定」として渡し、話に結ぶ(`episode_idea`)。
足した話は `key` / `start` / `title` / `viewpoint_character_id`(渡したときだけその id。渡さなければ NULL)/
`place_id`(渡したときだけその id)/ `text`(本文)を持つ。自動生成なので `synced` を立てる。
Claude のモデルの既定は `claude-sonnet-5` の `medium`(`ai_client.py` の `_MODEL` / `_EFFORT`)で、本文だけは
`claude-fable-5-1` の `high`(`EPISODE_MODEL` / `EPISODE_EFFORT`)で書く。本文のモデルは `model` / `effort` で差し替えられる
(この選択肢は本文を書く Claude 呼び出しにだけ効く一時的な値で、`episode` テーブルには残らない)。
`episode_id` を渡すと、話を足さずにその枠(同じ作品の、本文の無い話)へ書く。`key` / `time` / `viewpoint_character_id` /
`place_id` は省けば枠のものを使い、題は枠に題があればそれを残す。枠は前の話から外す。本文のある話・別の作品の話は書き換えずに止まる。
本文が得られなければ話を足さず(枠も変えず)に None を返す(`ai/time_keeper/frame_generator.py`)。

本文だけの生成(`fill_episode`)は、枠(`episode_id`)の種・時刻・視点・場所を使って本文を書き、同じ行の `text` に足す。
材料と書き方は話の生成と同じで、枠の空いている題は書いたときのもので埋める。`place_id` を省くと枠自身の `place_id`
(無ければ作品の立つ場所)を材料にする。渡すとその場所を材料にし、枠の `place_id` もその id にする。
種か時刻の無い枠・本文のある話は止まる(`ai/time_keeper/episode_generator.py`)。

上の表の「作る」「確定する」入口を使えば、Claude も対話の中で人物・場所・出来事の
内容を決めて確定してよい。

## 作り方

置き場所は `<領域>/<動詞_対象>.py`。領域はいまのところ次の七つ。

- `randomizer/` — ランダム生成(作る／確定する)と、確定済みレコードの修正
- `story/` — 作品・話(`story`/`episode`)まわりの読み書き(材料を引く・本文を確定する)
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
│   ├─ CommitEntrypoint         「確定する」系の共通処理(parse/check_columns/check_exists)。GUI の API も execute(session) を呼ぶ
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

(`meme.extract_memes.ExtractMemes`・`fact_check.check_facts.CheckFacts` は、`execute(session)` の外で
db セッションを開き直したいので `Entrypoint` を直接継ぐ)

## 引き方は query 側にある

読む側の中身は `data_access_logic/query/` にある。

| モジュール                     | 何のため                                                     |
| ------------------------------ | ------------------------------------------------------------ |
| `common_query.py`              | 時刻の扱い・断面・顔ぶれ・場所の道筋                         |
| `character_simulation_query.py` | 人物を軸に周辺を読む(`read_surroundings`)                   |
| `dictionary_query.py`          | アイデア(辞書)の検索。名前・本文(`idea_note` を左外部結合した追記も含む)の部分一致、場所・時刻の範囲、自動生成の候補 |
| `story_createion_query.py`     | 場所に掛かる作品(`story`)の読み出し                          |
| `world_createion_query.py`     | 生きている人物、広さの整合、進行中の判定               |
| `event_seed_query.py`          | 出来事の種をまだ抜き出していない元(`event_seeded` が false) |
| `review_query.py`              | ユーザの判断が要るもの(本文に残った TODO・世界観へ反映していない話) |

ここのファイルはその薄い呼び出し面で、**SQL は組み立てない。**
引く条件は時刻とレコードの id だけで表す。足りない引き方が出てきたら
query 側に関数を足して、ここに入口を一つ被せる。
