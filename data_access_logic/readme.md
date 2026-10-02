db を読み書きする処理と、それを呼ぶ入口を置く場所。claude と GUI の API は、どちらもここの処理を使う。
**claude が db を触る操作の前にこの readme を引く。**

入口は `<領域>/<動詞_対象>.py` に一つずつ置いたクラス。同じ入口を、呼ぶ側が次のように使い分ける。

- claude が CLI から: インスタンス化して `show()` を呼ぶ。結果を JSON で print する
  (CLI 引数のパースはしない。`if __name__ == "__main__"` も置かない)
- 結果を同じ python の中で続けて使う: print せずに返す `run()` を呼ぶ
- GUI の API: 自分の開いたセッションで `execute(s)` を呼び、レスポンスのモデルをそのまま使う

    from data_access_logic.location.list_locations import ListLocations
    ListLocations(kind="村").show()

db の触り方(入口越し・読み取り)は `.claude/docs/db.md` を見る。ユーザが見て直す窓口は `gui/`。
ここの入口は GUI の API(`POST /api/interface/<領域>.<ファイル>.<クラス>`)からも同じ引数で呼べる(`gui/readme.md`)。

## 引数とレスポンス

行の中身を渡す引数は、dict や JSON の文字列ではなく pydantic のモデルで渡す。モデルは領域ごとの
`data_access_logic/<領域>/form.py` にあり、スキーマに無い欄が混ざっていたらそこで止まる(`extra="forbid"`)。
修正の入口(`Update*`)は `id` 必須で、渡した欄だけを直す(省いた欄と、`None` を明示した欄は区別する)。

    from data_access_logic.location.commit_location import CommitLocation
    from data_access_logic.location.form import LocationCreateForm
    CommitLocation(LocationCreateForm(name="霧の村", kind="村", parent_id=2)).show()

| 入口 | 引数のモデル |
| --- | --- |
| `CommitLocation` / `UpdateLocation` | `location.form.LocationCreateForm` / `LocationUpdateForm` |
| `CommitCharacter` / `UpdateCharacter` | `character.form.CharacterCreateForm` / `CharacterUpdateForm`(子の行は `character.record.CharacterParameterRow` / `CharacterLocationRow` / `CharacterHistoryRow`) |
| `CommitCharacterLocation` / `UpdateCharacterLocation` | `character.form.CharacterLocationCreateForm` / `CharacterLocationUpdateForm` |
| `CommitCharacterRelation` / `UpdateCharacterRelation` | `character.form.CharacterRelationCreateForm` / `CharacterRelationUpdateForm` |
| `CommitEvent` / `UpdateEvent` | `event.form.EventCreateForm` / `EventUpdateForm` |
| `CommitIdea` / `UpdateIdea` | `idea.form.IdeaCreateForm` / `IdeaUpdateForm`(呼び名の行は `idea.record.IdeaRecognitionRow`) |
| `CommitMeme` / `UpdateMeme` | `meme.form.MemeCreateForm` / `MemeUpdateForm` |
| `CommitOracle` / `UpdateOracle` | `oracle.form.OracleCreateForm` / `OracleUpdateForm` |
| `CommitStylePreference` / `UpdateStylePreference` | `style_preference.form.StylePreferenceCreateForm` / `StylePreferenceUpdateForm` |
| `UpdateEventSeed` | `event_seed.form.EventSeedUpdateForm` |
| `CommitStory` / `UpdateStory` | `story.form.StoryCreateForm` / `StoryUpdateForm` |
| `CommitEpisode` | `episode.form.EpisodeCommitForm` |
| `GenerateFrame` / `CompletePlot` | `episode.form.EpisodeForm`(下書き。空の欄は指定なし) |
| `GenerateCharacter` | `character.form.CharacterForm`(下書き) |
| `GenerateEvent` | `event.form.EventForm`(下書き) |
| `SearchIdeas` / `ResolveTerms` | `idea.models.IdeaTerm` のリスト |

(モジュールはどれも `data_access_logic.` を頭に付ける)

`run()` は、入口が組んだレスポンスのモデルを `model_dump(mode="json")` した dict(一覧はそのリスト)を返す。
時刻は `"11579/03/02 00:00:00"` の文字列、`confirmed` は値の文字列になる。レスポンスのモデルは、行を写したものが
`data_access_logic/<領域>/record.py`(`*Record` など)、読む入口の組み立ては各領域の `reading.py`(出来事の行・人物の一覧表・話の題・作品の要約と断面)、入口だけのものはその入口のファイルにある。
GUI の API は JSON の dict を受け取り、入口の引数の型注釈に沿ってモデルに読み込んでから呼ぶ(`gui/api/interface.py`)。

## 依頼内容 → 呼ぶコード

`data_access_logic.` を頭に付けて import する。

| 依頼内容(言い回しの例)           | 呼ぶコード                                                                 |
| ---------------------------------- | -------------------------------------------------------------------------- |
| 「どんな場所がある?」「村の一覧」   | `location.list_locations.ListLocations(kind=None)`                                    |
| 「この場所の近くには何がある?」     | `location.list_neighbors.ListNeighbors(location_id, kind=None, limit=None)`。同じ星の他の場所の方角・距離・高低差を近い順に返す |
| 「人物の一覧」「誰がいる?」         | `character.list_characters.ListCharacters()`                                     |
| 「人物同士の関係は?」               | `character.list_character_relations.ListCharacterRelations(character_id=None)`   |
| 「出来事の一覧」                     | `event.list_events.ListEvents()`(全件)。絞るなら `event.read_events.ReadEvents(time=…)` か、`ReadEvents(location_id=…)` / `ReadEvents(character_id=…)` / `ReadEvents(event_id=…)`(どの表の id かを名前で渡す) |
| 「このアイデアは何?」「アイデアを調べて」 | `idea.search_ideas.SearchIdeas(keywords, location_id=None, limit=None, time=None)`。名前・本文(基本の本文と追記の両方)の部分一致のあいまい検索。`keywords` は `IdeaTerm(keyword=…, variants=[…])`(`variants` は言い換え)のリスト。当たり方の強い順に返す。自動生成の候補も返す。`location_id` は現在地から最上位までの場所に、`time` はその時刻に効く(`start` <= time < `end`)アイデアに絞る。`called` はその場所・時刻での作中の呼び名。`text` は `time` の時点に効く追記(下の「アイデアの追記」)まで積み重ねた本文 |
| 「この下書きに関わる設定は?」(中間段を自分で回す) | `idea.resolve_terms.ResolveTerms(terms, location_id=None, time=None)`。下書きから洗い出した語(`IdeaTerm`。`keyword` / `variants` / `description` / `kind` / `start` / `end`)をアイデアと照らし、当たったものと上位・下位を返す。当たらなかった語は候補として足す(下の「中間段」)。候補の効く期間は語の `start` / `end`。`start` は `time` と下書きの中身からある程度はっきり言えるときだけ付け(言えなければ省いて None)、`end` は分かるときだけ付ける。`time` は出来事の時刻。`time` を渡すと `start` が空(時期が未定)のアイデアは `ideas` に入れない。呼び名に当たったら本質のアイデアにそろえ、作中の呼び名を `called` に付ける |
| 「この本文が踏まえたアイデアを結んで」 | `idea.link_ideas.LinkIdeas(idea_ids, event_id=None, episode_id=None, character_id=None)`。三つのうち一つだけ渡す |
| 「この候補をあのアイデアにまとめて」 | `idea.merge_idea.MergeIdea(source_id, target_id)`。結んだ本文と source の認識(呼び名)を付け替えてから source を消す |
| 「判断待ちの一覧」                   | `review.list_pending_reviews.ListPendingReviews()`。候補のアイデア・候補のミーム・未同期の話・本文に残った TODO |
| 「場所を足して」                     | `location.create_random_location.CreateRandomLocation()` で下書き → 内容を決めて `location.commit_location.CommitLocation(location)` |
| 「人物を足して」                     | `character.create_random_character.CreateRandomCharacter()` → `character.commit_character.CommitCharacter(character)`。説明(人物の芯)は `text` に書く。持たせるミームは `meme.draw_memes.DrawMemes(person=True)` で引き、`text` の `# meme` 節と `# 行動原理` 節に書く(下の「人物が持つミーム」)。来歴の節目は、その年から始まる `histories` の行に一件ずつ書く(下の「人物の来歴」。サブキャラクターは世界の書き進めた所より後を書かない) |
| 「この場所にランダムな人物を何人か作って」「全国家に人物を生成」 | `character.generate_characters.GenerateCharacters(location_ids, time, count=(2, 4), person=True, seed=None)`。場所ごとに `count` の範囲の人数を、時の流れの中で生む人物と同じ自動生成(`data_access_logic/character/generator.py` の `generate_character`。性格・ミーム・来歴・名づけまで AI が決める)で作り、`time` の時点で生まれた歳にする。一人ごとに commit する。作品の無い場所が混ざっていれば作る前に止まる。`person=False` で人物以外の対象を作る。`confirmed=未確認` で足す(下の「出来事・人物の承認フラグ」) |
| 「出来事を足して」                   | `event.create_random_event.CreateRandomEvent()` → `event.commit_event.CommitEvent(event)` |
| 「この下書きから人物を AI に作らせて」 | `character.generate_character.GenerateCharacter(character=CharacterForm(...), time=None, seed=None, plot_text=None)`。欄の値(全部空でもよい)を核に、時の流れの中で生む人物と同じ自動生成(`generate_character`)で全欄を組み立て直して足す。名前・説明は核として渡し、性別・体格・口調・性格・種別・生年・没年・`main_character` は決まった値にする。`time`(現在の時刻)を省けば世界の最新の出来事の時刻。`plot_text` に登場させる話のプロットを渡せば、生年が決まっていなければ、その時刻・場所でその話の役どころ(下書きの説明)を果たせる年齢(0〜90歳。渡さなければ 0〜40歳)にする。説明・来歴には現在の時刻より後のこと(後年の姿・死)を書かず、没年は `main_character` を立てて渡したときだけ持たせる。`character` の `text` と `histories` の各行の説明は、人物像・役どころの下書きとして核にする。`character` に `id` を渡せば(GUI の詳細画面)、その人物の芯(`text`)が空のときに限り、決まっている名前・属性・出自を核に芯と来歴だけを書いて埋める(来歴の節目は今の行に足す。他の欄は変えない)。新しく作るときは `confirmed=未確認` で足す |
| 「この下書きから出来事を AI に作らせて」 | `event.generate_event.GenerateEvent(event=EventForm(...), seed=None)`。名前・記録を場面の指定に、時刻・場所・当事者を決まった値として出来事を一件起こす(下の「出来事の生成」)。時刻を省けば世界の最新、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。`event` に `id` を渡せば(GUI の詳細画面)、その出来事の本文(`text`)が空のときに限り、名前・場所・当事者から記録の本文だけを書いて埋める(`data_access_logic/event/writer.py`。他の欄は変えない)。新しく作るときは `confirmed=未確認` で足す |
| 「この人物の出自・居場所を足して」   | `character.commit_character_location.CommitCharacterLocation(location)`              |
| 「この二人の相関を足して」           | `character.commit_character_relation.CommitCharacterRelation(relation)`     |
| 「アイデアを足して」                 | `idea.commit_idea.CommitIdea(idea, fact_check=True)`。効く場所は `location_id`(その場所と配下で効く)、効く期間は `start` / `end`(出来事の時刻と比べる。空なら限らない)。`parent_idea_id` を渡さなければ、`kind` の分類アイデア(下の「アイデアの分類」)を `location_id` から自動で探して親にする(無ければ作る)。時代ごとの追記は `notes`(下の「アイデアの追記」)、場所・時代ごとの作中の呼び名は `recognitions`(下の「アイデアの認識(呼び名)」)。確定したあと、AI が Dラボのナレッジとネット検索でアイデアの妥当性・補足を検め、`fact_check` 欄(md の `# fact_check` 節)へ書く。続けて本文と検証結果のそれぞれからミームを抜き出し、足したミームも検める。`{"record": 確定したアイデア, "memes_added": 足したミームの件数}` を返す。`fact_check=False` で検めずに本文からだけ抜き出す |
| 「作中での呼び名を足して」「この場所・時代では〇〇と呼ぶ」 | `idea.commit_idea.CommitIdea(idea)` / `idea.update_idea.UpdateIdea(idea)` に `recognitions`(下の「アイデアの認識(呼び名)」)を付けて足す。呼び名を使う場所・時代は各行の `location_id` / `start` / `end`(空の列はどこでも・いつでも) |
| 「アイデア・oracle・ミームを検めて」「妥当性を調べて」 | `fact_check.check_facts.CheckFacts(table, ids=None, limit=None)`。`table` は `"idea"` / `"oracle"` / `"meme"`。AI が Dラボのナレッジ(優先)とネット検索で妥当性と補足を書き、`fact_check` 欄へ入れる。`ids` を省くと `fact_check` が空のものすべて(`limit` で件数を絞る)、渡すと検め済みでも検め直す。アイデア・oracle は検めたあと本文と検証結果からミームを抜き出し直し、足したミームも検める。`{"checked", "memes_added"}` を返す |
| 「場所を直して」                     | `location.update_location.UpdateLocation(location)`                                 |
| 「この人物の〇歳からの名字・背丈・口調・性格を決めて」「結婚して名字が変わる」 | `character.update_character.UpdateCharacter(CharacterUpdateForm(id=…, parameters=[...]))`。変わった時ごとの行の配列をまるごと渡す(下の「変わった時ごとのパラメータ」)。今の配列は `ReadCharacter` の `parameters` で読める |
| 「この人物の来歴を足して」「この人物の説明の移り変わりを足して」「〇年からの立場を記録して」「年の決まっていない構想を足して」 | `character.update_character.UpdateCharacter(CharacterUpdateForm(id=…, histories=[...]))`。起きた年ごとの行の配列をまるごと渡す(今の配列は `ReadCharacter` の `histories` で読む。時刻を渡すとその時刻までの行だけになるので、書き足すときは時刻を渡さずに読む)。年の決まっていない構想は `start` を空にした行に書く。下の「人物の芯と来歴」 |
| 「人物を直して」                     | `character.update_character.UpdateCharacter(character)`。名字・体格・口調・性格は `parameters` に、芯(説明・meme・行動原理・plot)は `text` に、来歴は `histories` に入れる(渡さなければ触らない)。出自・居場所は `character.update_character_location.UpdateCharacterLocation(location)`、相関は `character.update_character_relation.UpdateCharacterRelation(relation)` |
| 「場所を消して」                     | `location.delete_location.DeleteLocation(location_id)`                              |
| 「出来事を直して」                   | `event.update_event.UpdateEvent(event)`。`id` 必須、渡した欄だけ直す。`character_ids` を渡すと当事者をまるごと置き換える。直したあと要約(`event_summary`)を作り直す |
| 「出来事を消して」「出来事を作り直して」 | `event.delete_event.DeleteEvent(event_id)`。子の出来事が残っていれば止まる。当事者・アイデアとの中間テーブルの行と要約も消す。出来事で人物の `histories` に積み足した行と、足したアイデアの候補は残るので、要らなければ `UpdateCharacter` / `DeleteIdea` で別に戻す |
| 「アイデアを直して」                 | `idea.update_idea.UpdateIdea(idea)`。`id` 必須、渡した欄だけ直す。`notes` / `recognitions` を渡すとそれぞれ配列をまるごと置き換える(下の「アイデアの追記」「アイデアの認識(呼び名)」) |
| 「アイデアを消して」                 | `idea.delete_idea.DeleteIdea(idea_id)`。下位のアイデアが残っていれば止まる。結んだ本文との中間テーブルの行、認識(呼び名)・追記の行も消す |
| 「覚え書きを足して」「oracle に書いて」 | `oracle.commit_oracle.CommitOracle(oracle, fact_check=True)`。`text` 必須。題は `title`。確定したあとは `CommitIdea` と同じく、検めて(`fact_check`)、本文と検証結果のそれぞれからミームを抜き出し(`memes_added`)、足したミームも検める |
| 「覚え書きを直して」                 | `oracle.update_oracle.UpdateOracle(oracle)`。`id` 必須、渡した欄だけ直す |
| 「ミームを足して」「この考え方をミームに入れて」 | `meme.commit_meme.CommitMeme(meme)`。`text` 必須。`category` は 信条/欲求/境遇/集団/理 のいずれか(空でもよい。次の抽出で AI が振る)。ユーザが書いたものなので `confirmed` を渡さなければ 承認 で入れ、置き場所は分類のディレクトリ |
| 「ミームを直して」「ミームの分類を直して」 | `meme.update_meme.UpdateMeme(meme)`。`id` 必須、渡した欄だけ直す。`category` は 信条/欲求/境遇/集団/理 のいずれか |
| 「ミームを消して」                   | `meme.delete_meme.DeleteMeme(meme_id)`                                 |
| 「出来事の種を直して」               | `event_seed.update_event_seed.UpdateEventSeed(seed)`。`id` 必須、渡した欄だけ直す。語の置き換えなどは db を読んで id を拾ってから呼ぶ |
| 「ミームを抜き出して」               | `meme.extract_memes.ExtractMemes()`。アイデア・oracle(著者の覚え書き)の本文と検証結果(`fact_check`。別々の元として渡す)・人物の筋書き(`# plot`)・出来事の本文から抜き出し、分類を振って `confirmed=未確認` で `meme` テーブルへ足す。既にあるミームと同じ考え方の言い換えは足さない。最後に、分類の空いたミーム(手で足したものなど)に分類を振る。足したミームは AI が Dラボのナレッジとネット検索で検め、`fact_check` 欄へ書く(`ExtractMemes(fact_check=False)` で飛ばす)。足した件数を `{"memes_added"}` で返す。抜き出しただけでは `DrawMemes` に出ず、ユーザが GUI で承認するまで、人物へ引く・書き込む文脈には使われない(「判断待ちの一覧」に候補として出る) |
| 「ミームを引いて」                   | `meme.draw_memes.DrawMemes(person=True, seed=None)`。ユーザが確かめた(`confirmed=承認`)ミームだけから、分類ごとに 0〜2 件引き、それぞれに古今表裏を割り振って返す。db には書かない |
| 「ミームと要約の取りこぼしをまとめて作って」 | `meme.refresh_generated_content.RefreshGeneratedContent()`。`ExtractMemes` に加えて、まだ要約の無い出来事・話もすべて見て `event_summary` と話の `summary_text` を作る。`CommitEvent` / `CommitStory` / `CommitEpisode` は確定した一件だけを見るので、GUI から直した分などの取りこぼしを拾うのはこちら |
| 「作品の一覧」                       | `story.list_stories.ListStories()`                                           |
| 「話を書き始める」「次の話を書く」   | `story.start_story.StartStory(story_id)`。同期確認・見出し・直前の話・断面・顔ぶれを一度に出す |
| 「前の話を読ませて」                 | `episode.read_episodes.ReadEpisodes(story_id, count=10, before=None, text=True)`。`before` は時刻で、start がそれより前の話に絞る |
| 「その時点の顔ぶれは?」             | `story.read_cast.ReadCast(story_id, time=None)`                              |
| 「その場所・その時点の様子は?」     | `story.read_brief.ReadBrief(location_id, time)`                                 |
| 「この人物の周りで何が起きている?」 | `character.read_surroundings.ReadSurroundings(character_id, time)`               |
| 「この人物を本文用にそろえて」       | `character.read_character.ReadCharacter(character_id, time=None)`。体格・口調・性格は `time` の時点の値を上の段に出す(`time` を省くと生まれたときの値)。変わった時ごとの行は `parameters`。芯は `text`。来歴(`histories`)は `time` の年までに起きた行だけを古い順に出す(`time` を省くと、年の決まっていない行も最後に含めてすべて) |
| 「作品を作る」「筋書きを足して」     | `story.commit_story.CommitStory(story)`。筋書きは作品の `text` に書く        |
| 「この作品の子に章・外伝を作って」   | `story.commit_story.CommitStory(StoryCreateForm(name=…, parent_story_id=<親の作品id>, …))`。付け替えは `UpdateStory(StoryUpdateForm(id=…, parent_story_id=…))`(自分か子孫の子にはできない。`None` を渡せば親から外す)。子の作品の話を書くときは、親をたどった作品の筋書き(`親の作品`)と、一番上の作品とその子孫の話を前の話として渡す(下の「話の生成」) |
| 「作品を直して」「筋書きを直して」   | `story.update_story.UpdateStory(story)`                                      |
| 「作品を消して」                     | `story.delete_story.DeleteStory(story_id)`。話か子の作品が残っていれば止まる |
| 「この下書きから話の枠を AI に決めさせて」 | `episode.generate_frame.GenerateFrame(frame=EpisodeForm(story_id=…, viewpoint_character_id=…, location_id=…, character_ids=[…], …), character_ids=None)`。下書きを枠として保存してから、題・プロット(`## 場面` / `## 狙い` の形)・時刻を下書きを核に AI が決める(`id` を渡せばその本文の無い枠を決め直す)。時刻は下書きにあればそれ、無ければ直前の話の後から AI が選ぶ。視点(`viewpoint_character_id`。Character への FK)・場所(`location_id`。Location への FK)は AI には決めさせず、下書きにあればその id をそのまま使う(無ければ NULL のまま)。登場人物は `character_ids`(省けば下書きの `character_ids`、それも無ければ枠の `episode_character`)で、足した枠の `episode_character` にも残す。書き直したプロットに名前が出る既存の人物は `mentioned` の行として登録し(下の「名前だけ出る人物」)、その設定を AI に渡す |
| 「プロットを補完して」「プロットを場面まで書き直して」「足りない人物・舞台を作って」 | `episode.complete_plot.CompletePlot(episode=EpisodeForm(story_id=…, character_ids=[…], …), order=None, model=None, effort=None)`。プロット補完。今のプロット(`plot_text`)を核に、`order`(作者の注文。展開・焦点・雰囲気など)も取り入れて、本文全体を場面に割ったプロット(下の「補足」の `## 場面` / `## 狙い` の形)を AI に書き直させ、それでプロットをそっくり置き換える(今のプロットの中身は書き直したプロットに含めさせる。本文は書かない)。書き直したプロットに出るのに登場人物にいない人物は `generate_character` で作って承認済みにし、話の `episode_character` に足す。書き直したプロットの主な舞台が話の場所(無ければ作品の立つ場所)より細かく、その直下の既知の場所にも無ければ、その場所の下に作って話の `location_id` にする。プロットか時刻が空なら先に `GenerateFrame` と同じ生成で枠を決める。登場人物は下書きの `character_ids`(話の `episode_character` と同じ欄)、省けば枠の `episode_character` で、空なら止まる。`model` / `effort` はプロットの書き直しと候補の呼び出しにだけ効く(省けば opus 5.5 の low)。書き直したプロットに名前が出る既存の人物は `mentioned` の行として登録し(下の「名前だけ出る人物」)、その設定を AI に渡す |
| 「この話を推敲して」「初登場キャラの描写を厚くして」 | スキル `revise-episode`。このセッションの Claude が `ReadEpisodeBrief` で材料を読んで自分で書き直し、`CommitEpisode` で確定する(`synced` はそのまま渡し、指示はプロットの「## 推敲」の節に積む。登場人物・場所が変わるなら、書く前に `CastEpisode` で結び直して材料を読み直す) |
| 「本文を確定する」「話のプロットを入れる」 | `episode.commit_episode.CommitEpisode(episode)`。`id` を渡せばその話を直し(渡した欄だけ)、省けば `story_id` の作品に新しい話を足す。`synced` を渡さなければ同期していない扱い(false)にする。`plot_text`(プロット)か `main_text`(本文)のどちらかがあればよい。`main_text` は `ai/instructions/style.py` の `layout_novel_text` で改行を整えてから入れる(地の文は一文一行、「◇」の行は空行二つ)。話に番号は無く、作品の中では `start` の順に並ぶ(`start` の無い話は後ろに id 順)。あいだに話を足すときは、前後の話のあいだの `start` を付ける |
| 「未同期の話は残ってる?」           | `episode.list_unsynced_episodes.ListUnsyncedEpisodes(story_id=None)`           |
| 「話を別の作品(章)へ移して」       | `episode.move_episodes.MoveEpisodes(episode_ids, story_id)`。話の作品を付け替える。本文・要約・同期フラグはそのまま |
| 「話を消して」                       | `episode.delete_episode.DeleteEpisode(episode_id)`。登場人物・踏まえたアイデアとの中間テーブルの行も消す。本文から足した出来事・アイデアの候補・ミームは残るので、要らなければ別に消す |
| 「世界観へ反映済みにする」           | `episode.set_episode_synced.SetEpisodeSynced(episode_id, synced=True)`   |
| 「話の要約を作り直して」「要約がおかしい」 | `episode.rewrite_episode_summary.RewriteEpisodeSummary(episode_ids)`。本文が変わっていなくても、話の概要(`episode.summary_text`)を AI に作り直させ、一件ごとに commit する。本文が変わったときの作り直しは `CommitEpisode` などが自動で行うので、これは中身の崩れた要約を直すとき用 |
| 「この場所・この時の出来事を起こして」「ヴァレンツァで11579/03/02に〇〇な場面」 | `event.generate_event.GenerateEvent(event=EventForm(location_id=…, time=…, name="〇〇な場面"))`。当事者はその時刻にそこにいて手の空いたサブキャラクターから選ぶ(下の「出来事の生成」)。当事者を決めるなら `character_ids` |
| 「このプロットで話を書いて」「〇〇と△△が出る話を 11579/03/02 で」「この枠に本文を書いて」 | スキル `episode`。このセッションの Claude が `ReadEpisodeCasting` でプロットから登場人物・場所を推測して `CastEpisode` で結び、そのあと材料を `ReadEpisodeBrief` で読んで自分で本文を書き、`CommitEpisode`(`synced=True`)で確定する(新しい話は先に `CommitEpisode` で枠を足す) |
| 「この話の登場人物・場所を決める材料を読ませて」 | `episode.read_episode_casting.ReadEpisodeCasting(episode_id)`。この話(題・時刻・場所・視点・プロット)・今の登場人物・名前だけ出る人物・登場人物の候補(プロット・本文に名前が出る人物・登場人物と関係のある人物・話の場所にいる人物)・話の場所の中の既知の場所と、登場人物・名前だけ出る人物それぞれがこの話より前に関わったすべての話(作品を問わない。概要つき)を、日本語の見出しと id 付きで返す。関わった話の概要が無いか本文と食い違っていれば、読む前に AI で作り直す(作れなかった話は null)。時刻が空なら止まる |
| 「人物を消して」 | `character.delete_character.DeleteCharacter(character_id)`。期間ごとの値・説明の変化・出自と居場所・相関・結んだアイデア・話に名前だけ出る行も消す。出来事の当事者か、話の登場人物・視点になっている人物は止まる |
| 「この話を id で読ませて」「人物が関わった話の本文を読みたい」 | `episode.read_episode_texts.ReadEpisodeTexts(episode_ids)`。作品・題・時刻・プロット・本文・概要を時刻の順に返す |
| 「名前だけ出る人物を拾い直して」 | `episode.refresh_mentions.RefreshMentions(episode_ids=None)`。今のプロット・本文から `episode_character` の `mentioned` の行を拾い直す(省けばすべての話)。拾い直しは保存のときにしか走らないので、古い話やあとから人物を足した話の取りこぼしを埋める。登場人物の行は変えない |
| 「この話の登場人物・場所を結んで」 | `episode.cast_episode.CastEpisode(episode_id, character_ids, location_id=None, viewpoint_character_id=None)`。登場人物(`episode_character`)をまるごと置き換え、登場人物と視点の人物を承認し、名前だけ出る人物を拾い直す。場所・視点は渡したときだけ書く。同期フラグは変えない |
| 「この話を書く材料を読ませて」 | `episode.read_episode_brief.ReadEpisodeBrief(episode_id)`。書き方(文体の決まりと `style_preference` の `shared` / `episode` の行)・作品・前の話の概要(この話より前の、同じ作品のすべての話と登場人物が関わったすべての話)・文体の見本(同じ作品の直前の五話の本文。中身は読ませない)・この話(題・時刻・同期・場所・視点・登場人物・名前だけ出る人物・関係・プロット・今の本文)・場所の直近の出来事・後に決まっている出来事を、日本語の見出しと id 付きで返す。登場人物の直近の出来事・関係と場所の出来事は話に結んだ登場人物・場所から引くので、先に `CastEpisode` で結んでから読む。時刻が空なら止まる。前の話・出来事の要約が本文と食い違っていれば、読む前に AI で作り直す(本文は書かない) |

**まだ入口が無いもの**(頼まれたら作ってから行う): 人物の削除。

筋書きのテーブルは無い。場所に掛かる筋書きは作品(`story`)の
`text` に、人物に掛かる筋書きはその人物の `text` の `# plot` の節に書く。

**変わった時ごとのパラメータ**: 人物の名字(`family_name`)・体格(`sex` `height` `build`)・口調(`first_person` `second_person` `third_person` `tone` `dialect`)・
性格(12 軸。無/低/並/高/必)は、`character_parameter` テーブルに、値の変わった時ごとの行で持つ。入口では人物の
`parameters` に配列で並ぶ(id と character_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。

```json
"parameters": [
  {"start": "11585", "height": 140.0, "tone": "負けず嫌いで声が大きい", "sincerity": "並", ...},
  {"start": "11600", "height": 175.0, "tone": null, ...}
]
```

- 行は終わり(`end`)を持たず、`start` から先ずっと効く。`start` が空なら初めから効く
- 空の欄は「この行では決めない」。ある時刻の値は、その時刻までに始まった行を、始まりの古い順に重ねて決める
  (後に始まる行、同じなら後の行が勝つ)。どの行も決めていない性格の軸は「並」。値を変えたいときは、変わった時を `start` にした行を足す
- 時刻を渡さずに引くと、始まりの無い行と一番早く始まる行(生まれたときの値)だけを重ねる
- 人物の誕生(`start`)は専用の列を持たず、この `parameters` の一番早く始まる行の `start` で表す。死亡(没年)は人物の `end` 列に持つ。
  `CommitCharacter` / `UpdateCharacter` へは人物の欄としてトップレベルの `start` / `end` を渡せばよく、`start` は入口が該当する行へ書き込む。
  読み出し(`ReadCharacter` など)も人物の `start` / `end` としてそのまま出る。死んでいない人物・対象では `end` を空にする
- 出来事の生成(`GenerateEvent`)は、出来事の時刻の値を使う。人物の自動生成・`CreateRandomCharacter` は一行だけを作る
- `CommitCharacter` / `UpdateCharacter` は `parameters` を受け取る。`UpdateCharacter` に渡すと配列をまるごと置き換える
- `name` は名字を含めない名だけを持つ。名字は `family_name` に分け、結婚・養子・家の取り立てなどで変わるなら、
  変わった時点からの行を足す。名字を持たない身分なら空。`CreateRandomCharacter` の下書きでは空なので、
  出自・身分・土地柄から決めて入れる(時の流れの中で生む人物は、名づけのときに AI が決める)

**人物の芯と来歴(text / character_history)**: 人物の芯(説明・`# meme`・`# 行動原理`・`# plot`)は人物の `text` に書く。
芯は時期を限らない説明で、いつの話・出来事にも人物像として渡る。時が進むにつれて起きたこと・変わった立場・境遇などの来歴は、
`character_history` テーブルに起きた年ごとの行(`start` / `description`)で積む。入口では人物の
`histories` に配列で並ぶ(id と character_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。
アイデアの基本の本文(`text`)と追記(`notes`)と同じ分け方で、GUI の見た目は「アイデアの認識(呼び名)」に揃えている。

```json
"text": "村の鍛冶屋。…\n\n# meme\n- 古表: …\n\n# 行動原理\n…",
"histories": [
  {"start": 11585, "description": "村の鍛冶屋に徒弟として入る"},
  {"start": 11600, "description": "師の死後、鍛冶屋を継ぐ\n隣村の娘を妻に迎える"},
  {"start": null, "description": "(年未定)いずれ鍛冶屋を畳み、都へ出る"}
]
```

- `start` は年の整数(時刻ではない)。行は終わり(`end`)を持たず、その年から先ずっと効く
- `start` が空の行は、起きる年がまだ決まっていない構想(主要人物の先の移り変わりなど)。作者が読むとき(時刻を渡さない
  `ReadCharacter`・GUI)だけ出し、話・出来事・人物の生成の材料には渡さない。年が決まったら `start` を入れる
- 行を増やしすぎないよう、一人の人物について一年に一行にする。同じ年のことは、その年の行の説明に改行して書き足す
- `description` は必須。来歴の節目はその年を `start` にした行に書き、芯は `text` に書く(来歴の行に芯を書かない)
- 話・出来事・人物の生成に渡す材料は、芯(`text`。人物像)と、その時刻の年までに起きた行(`start` <= 時刻の年)だけを古い順に並べた来歴
  (`data_access_logic/character/histories.py` の `histories_at`)。先の年から始まる行や年の決まっていない行を書き足しても、それより前の話・出来事には効かない
- 来歴を書き足すときは、既にある説明を書き換えず、起きた年の行があればその説明の末尾に足し、無ければその年を `start` にした行を足す
  (`UpdateCharacter` は配列をまるごと置き換えるので、時刻を渡さない `ReadCharacter` で今の行をすべて読み、足した配列を渡す)
- `CommitCharacter` / `UpdateCharacter` は `text` と `histories` を受け取る。`UpdateCharacter` に `histories` を渡すと配列をまるごと置き換える
- 出来事の生成(`GenerateEvent` など)で人物について分かったことは、出来事の年の行に足す(`add_history`)

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
- `SearchIdeas` の名前・本文検索、`data_access_logic/idea/search.py`(あいまい検索の当たり方の判定)、清書に渡す
  「関係する設定」(`data_access_logic/idea/models.py` の `IdeaContextSerialized`)は、いずれもこの積み重ねた本文を使う

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
- `SearchIdeas` の名前・本文検索、`data_access_logic/idea/search.py`、`data_access_logic/idea/context.py`(中間段)、清書に渡す「関係する設定」
  (`IdeaContextSerialized`)は、いずれもアイデアの `recognitions` を見て、当てはまる場所・時代の
  認識があればその `name` で呼び、`detail` を「作中での受け止め方」として添える。当てはまる認識が無ければ本質の `name` をそのまま使う
- ある場所・時代の認識(呼び名)がある行は、清書のプロンプト(`ai/instructions/idea_context.py`)で
  「その場所・時代の人物はこの名前を認識しているもの」として扱われ、本文ではその名で呼ぶ
- `MergeIdea` は `source_id` の `recognitions` を `target_id` へ付け替えてから `source_id` を消す。
  `DeleteIdea` は下位のアイデアが残っていなければそのまま消し、`recognitions` も一緒に消える

**アイデアの分類(親の自動探索)**: `parent_idea_id`(上位のアイデア)は、`kind` ごとに一つ、その kind を
まとめる「分類」のアイデア(`name` が `kind` と同じ。例: `name="組織" kind="組織"`)を親にしてぶら下げる。
`CommitIdea` に `parent_idea_id` を渡さなければ(中間段(下の「中間段」)が候補を足すときも同様)、
`data_access_logic/idea/classification.py` の `find_or_create_classification` が `location_id` の場所チェーンを
根まで遡り、対応するアイデア(たいていは「星」のアイデア)が見つかった一番深いところを探して、その配下で
`kind` の分類を探す。あれば再利用し、無ければ `name=kind` の分類を新しく作って親にする(`confirmed=承認`)。
場所チェーンのどこにも対応するアイデアが無ければ親を決めようがないので、`parent_idea_id` は空のまま
(明示的に渡した `parent_idea_id` はそのまま尊重し、自動探索はしない。分類自体を足すとき(`name == kind`)も、
自分自身の親を探しに行かない)。

人物の来歴は、節目の年を `start` にした `histories` の行に、
`<何があり、立場・仕事・住まい・人間関係がどう変わったか>` を `description` として書く(同じ年の節目は一行にまとめる)。人物説明にある立場・仕事・住まいには、いつそうなったかの節目を必ず入れる。
「現在」の行は要らない。話・出来事の材料にはその時刻までに始まった節目だけが渡るので、後年の立場を先取りしない。

サブキャラクター(`main_character` が false の人物・対象)の `histories` には、世界の書き進めた所(本文のある話の一番新しい `start`)より後のこと
(後年の立場・死・「# 未来」の節・`# plot` の先の筋・その時より後に始まる行など)を書かない。没年(`end`)と、居場所(`character_location`)の境目より後の始まり・終わりも入れない。出来事の生成はサブキャラクターを当事者に選ぶので、
決まった未来があると、生成した出来事や進めたメインの出来事と食い違いやすくなるため。来歴は話の本文で起きたことを、
話を確定するたびに足していく(スキル `episode` の「確定のあと」)。人物の自動生成(`generator.py`)も、説明・来歴に現在の時刻より後のことを書かせず、サブキャラクターには没年を持たせない。プロット補完で作る人物には話のプロットを渡し、その役どころに合う年齢にする。主要人物(`main_character` が true)は、作者の構想として未来まで書いてよい。未来の節目は、その年を `start` にした行にすれば、それより前の話・出来事には渡らない。年がまだ決まっていない構想は `start` を空にした行に書けば、どの話・出来事にも渡らない。芯(`text`)の `# plot` はいつの話・出来事にも渡るので、先の筋を前の話に見せたくなければ、来歴の行に書く。

人物が持つミーム(行動原理の芯。`meme` テーブル)も専用の節は無く、その人物の `text` の
`# meme` 節に、持つミームの文面を `- <古今表裏>: <文面>` の箇条書きでそのまま書く。
人物は複数のミームを持ってよい。ミームどうしの関係の整理は、`# meme` ではなく `# 行動原理` 節に書く
(`# plot` に書くと、そこからミームがまた抜き出される)。

- 古今表裏: 古=かつて持っていたが今は手放した / 今=いま持っている / 表=人前で掲げている / 裏=内に秘めている
- 引き方: 分類ごとに 0〜2 件。人物は 信条・欲求・境遇、人物以外の対象は 信条・欲求・集団 から引く。
  理(世界の法則)は引かない(`data_access_logic/constants.py` の `MEME_*`)
- ユーザが確かめた(`confirmed=承認`)ミームだけを引く。抜き出したばかりの `confirmed=未確認` のミームと、退けた `非承認` のミームは、
  GUI のレビューで確かめられるまで、出来事の生成・人物生成のどちらでも文脈に取り入れられない
- 人物の自動生成(`data_access_logic/character/generator.py`)は、この引き方と整理を自動で行う

## 出来事・人物の承認フラグ

`event` / `character` も `confirmed`(未確認/承認/非承認)を持つ。列の既定値は 承認(GUI から手で足す・
`CommitEvent` / `CommitCharacter` で確定するときは渡さなければ 承認)だが、AI の自動生成
(`GenerateCharacter(s)` / `GenerateEvent`)は明示的に
`confirmed=未確認` で足す。ユーザが GUI のレビュー画面(`reviewable=True`)で確かめて 承認 にするまで:

- `GenerateFrame` は、登場人物(下書きの `character_ids`。
  省いたときは話の `episode_character`)に未確認・非承認の人物が混ざっていると止まる
- 話に渡す材料(場所の直近の出来事・登場人物それぞれの直近の出来事)も、未確認・非承認の出来事は使わない
- `ReadCast` / `ReadBrief` の顔ぶれ、`ReadSurroundings` の周りの人物・出来事にも、未確認・非承認は出てこない

(「この時点より後に既に決まっている出来事」は、まだ確かめていない出来事でも矛盾を避けるために渡す。
出来事の生成(`GenerateEvent`)の候補選び・当事者選びも、承認済みに絞らない)

## 中間段(下書き → 語の洗い出し → 清書)

本文を書く生成は、下書き(一段目)と清書(二段目)のあいだに、アイデアと照らす中間段を挟む
(`data_access_logic/idea/context.py`)。

1. 下書きから、設定資料と照らす語とその言い換えを AI に挙げさせる(`data_access_logic/idea/search.py` の `keywords_of`)。
   出来事の時刻と下書きの中身から、語ごとの `start` / `end` も決めさせる。ある程度はっきりした `start` が言えない語は null、`end` は分かる語だけ
2. 語と言い換えで、アイデアの名前・本文(場所・時代ごとの作中の呼び名 `idea_recognition` の `name` / `detail` も含む)を
   部分一致で引く(`data_access_logic/idea/search.py` の `search`)。その場所・時刻で効くアイデアだけ。
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
| 人物の自動生成 | 中身を決めた説明 | 関係する設定があれば説明を清書 |
| プロット補完(`data_access_logic/episode/plot_completer.py`) | 今のプロット(`plot_text`) | 書き直したプロット |

claude が対話で書くときは、自分で語と言い換えを挙げて `ResolveTerms` を呼び、返った `ideas` を踏まえて清書し、
確定したあとに `hits` と `candidates` の id を `LinkIdeas` で結ぶ。

`meme` テーブル自体はアイデア(`idea`)・oracle・人物の筋書き・出来事から抜き出して貯めるだけで、
人物との FK は持たない(ミームは人物の間を移り変わり・伝染していくため)。

補足:

- `CommitEvent` / `UpdateEvent` / `CommitStory` / `CommitEpisode` は、確定したあとに毎回(`ai_entrypoint.py` の `CommitAndRefresh`)
  ミームの棚卸し
  (`data_access_logic/meme/extractor.py` の `refresh`)と、出来事・話ならその場での要約(`event_summary` / 話の `summary_text`。
  本文が変わっていれば作り直す)をまとめて行うので、`ExtractMemes` を別に呼ぶ必要は無い。`CommitEvent` はさらに出来事の種を抜き出す
  (下の「出来事の生成・話の材料」)。確定の入口を通らなかった分の
  取りこぼしをまとめて拾いたいときは `RefreshGeneratedContent` を呼ぶ。これらの経路で足したミームは
  検めない(`fact_check` が空のまま)ので、`CheckFacts("meme")` で後から埋める
- 話は `episode` テーブルに一話一行で持つ。枠(`plot_text`。作者が入れるプロット、AI 生成前)と
  本文(AI か作者が書く、投稿する本文。`main_text`)を同じ行に持ち、時期・場所・視点は
  `start` / `end` / `location_id`(Location への FK)/ `viewpoint_character_id`(Character への FK)に入る。
  登場人物は `episode_character`(中間テーブル、多対多)で持つ。字数(`letters`)は本文から数える。
  `episode_character` の `mentioned` が true の行は、登場せずプロット・本文に名前が出るだけの人物(下の「名前だけ出る人物」)。
  本文の概要(`summary_text`)と、概要を作った本文の sha256(`summary_source_hash`)も同じ行に持つ。
  書いたモデル・effort は db に残さない(選択肢はその場の Claude 呼び出しにだけ効く)
- 本文に字数の指定は無い(`ai/instructions/style.py` の `EPISODE_STYLE_BASE`)。プロット(`plot_text`)と、渡された作品・登場人物・場所・
  直前の話・関係する設定などの周辺データを踏まえ、具体的な描写・会話・人物の動きまで詳しく書き起こす。
  場面の数と一場面の長さは決めず、中身に合わせる。**書く直前にプロットを場面まで割ってから本文に入る**。プロットはその話ぶんで 300〜500 字を目安に、
  `## 場面` の箇条書き(`場所 / 出る人 / そこで変わること`)と `## 狙い` で書く:

```
# plot_text
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
  閉じて揃える)で `CommitLocation` / `UpdateLocation` から入れる。経緯度が無い面の場所
  (大陸など)にも持たせられ、地図では薄い面として描く

## 出来事の生成・話の材料

世界の舞台設定や、既存の話から抽出した文体の癖のような「ユーザーの好み」は `core` には定数で持たず
(`ai/instructions/style.py` の `style_instruction()` を見る)、db の `style_preference` 表に対象(`target`)ごとに持つ。
話の本文の材料(`ReadEpisodeBrief` の「書き方」)には、`shared`(どの対象にも効く)と `episode` の行を足す(`style_preference/extras.py`)。
行が無ければ空で、`core` だけの汎用の文体になる。

出来事の生成(`GenerateEvent`)は、下書きの名前・記録を場面の指定(「市場の喧嘩」「怪談」など)に、時刻・場所・当事者を決まった値として、
候補をサイコロ → 記録(`data_access_logic/event/progress.py`)の順で一件起こす。
本文は小説ではなく、当事者の行動・言動を起きた順に整理した10行程度の要約(`ai/instructions/event_writing.py` の `EVENT_RECORD_INSTRUCTION`)。
世界ごとの文体の好み(`style_preference`)は使わない。
当事者を省けば、その時刻にその場所にいて(`character_location`)、別の出来事の最中でない、生きているサブキャラクターから選ぶ。
場所を名指しするので、場所の `active_random_generation` は見ない。作品の本文(筋書き)は渡さない。
出来事の候補は、出来事の種(`event_seed` テーブル)からランダムに引いた種か、直前の出来事からの連想で立てる。
種は作品の本文・話のプロット(`plot_text`、無ければ本文)・人物の `# plot` の節・出来事の本文から、時代・場所・固有名詞を抜いて抜き出したもの
(`data_access_logic/event_seed/extractor.py` の `refresh`。`event_seeded` が false の元だけから抜き出して true にする。
似た種は `consolidate` でまとめる)。抜き出しは、出来事を足す入口(`CommitEvent` / `GenerateEvent`)が、足したあとに
確定とは別のセッションで行う(足した出来事自身の本文も元になる。AI が答えなくても出来事は残る)。
GUI の表から足したとき(`execute(s)`)は抜き出さず、次に入口から出来事を足したときにまとめて拾う。
その場所か当事者に掛かる「この時点より後に既に決まっている出来事」は、要約を添えて記録を決める段に渡し、矛盾させない。
起こした出来事は `confirmed=未確認` で足す。

話の本文は、生成関数ではなくこのセッションの Claude が書く・直す(スキル `episode` / `revise-episode`)。
材料は `ReadEpisodeCasting` / `ReadEpisodeBrief`(`data_access_logic/episode/brief.py`)で読み、`CommitEpisode` で確定する。
枠の生成(`GenerateFrame`)・プロット補完(`CompletePlot`)は、渡した値をまず話の行(枠)と登場人物(`episode_character`)として保存し
(`data_access_logic/episode/form.py`)、その行だけから材料を読む(`data_access_logic/episode/material.py`)。
話に渡す登場人物は、話と人物のリレーション(`episode_character`)だけ。`character_ids` を渡せばそれでリレーションを置き換え、
省けば枠の `episode_character` を使う。

**名前だけ出る人物**: 登場人物でなく、プロット・本文に名前が出る承認済みの人物・対象は、`episode_character` に
`mentioned=true` の行として持つ(`data_access_logic/episode/mentions.py` の `save_mentions`)。話の下書きを保存するとき
(`save_frame`。`GenerateFrame` / `CompletePlot` の始め)と、枠の生成・プロット補完で
AI の結果を書き戻したとき、`CommitEpisode` / `CastEpisode` で確定したときに、今のプロット・本文から拾い直して置き換える。名前は、前後が名前の端と同じ字種(カタカナ・漢字・英数)で
続かない所だけを語として数え(「セラ」は「セラフィナ」に当たらない)、一字の名前は拾わない。
登場人物の `character_ids` は `mentioned` でない行だけで、置き換えても `mentioned` の行は残す(登場人物にした人物の行だけ消す)。
本文・プロット・枠を書く材料には「名前だけ出る人物」として、その時点の歳・種別・口調・人物像を渡す(直近の出来事・相関は渡さない)。
話のレコードでは `mentioned_character_ids` に並ぶ。
前の話は、この話の時刻より前の、本文のある話から選ぶ(`data_access_logic/episode/summary.py`)。
話の中身は概要だけで渡す。同じ作品のすべての話と、登場人物が関わった(`episode_character` に登場か名前だけの行がある)すべての話を、
作品を問わず重ならないように合わせて渡す(直前の話も含む)。
同じ作品の直前の五話(`constants.EPISODE_STYLE_SAMPLE_COUNT`)は校正済みとみなし、「文体の見本」として本文だけを渡す。
見本からは文体だけを汲ませ、中身は読み取らせない(`ai/instructions/past_episodes.py`)。章・外伝をまたぐ話には作品名を添える。作品の筋書きは、親の作品を「親の作品」としてたどって渡す。
枠を作るとき(`framer`)は本文を渡さず、前の話をすべて概要で渡す。
概要の無い話は書く前に作る(本文が変わっていなければ作り直さない)。
登場人物ごとに、その時点の歳・人となり・口調・相関・直近の出来事(要約)を渡す。話の場所(無ければ作品の立つ場所)の
直近の出来事と、その場所か登場人物に掛かる「この時点より後に既に決まっている出来事」も渡し、矛盾させない。
プロット補完では、プロットから中間段でアイデアを引いて「関係する設定」として渡す。
Claude のモデルの既定は `claude-opus-5-5` の `low`(`ai/claude_code/ai_client.py` の `_MODEL` / `_EFFORT`)。

上の表の「作る」「確定する」入口を使えば、Claude も対話の中で人物・場所・出来事の
内容を決めて確定してよい。

## 作り方

入口の置き場所は `<領域>/<動詞_対象>.py`。領域は扱うテーブルで分け、その領域のマテリアル(`models.py`)・
引数のモデル(`form.py`)・レスポンスのモデル(`record.py`)・生成の処理と同じディレクトリに入口を並べる。

- `location/` — 場所(一覧・近く・下書き・確定・修正・削除)
- `character/` — 人物・居場所・相関(一覧・本文用の読み出し・周り・下書き・確定・修正・AI 生成)、相関図(`relation_graph.py`)
- `event/` — 出来事(一覧・絞り込み・下書き・確定・修正・削除・AI 生成)
- `event_seed/` — 出来事の種の修正
- `story/` — 作品(一覧・書き始め・断面・顔ぶれ・確定・修正・削除)
- `episode/` — 話(読み出し・未同期・確定・削除・同期フラグ・作品の付け替え・AI の枠・プロット補完・Claude が自分で書くための材料)
- `idea/` — アイデア(検索・確定・修正・削除・統合)と中間段(下書きの語をアイデアと照らす・本文とアイデアを結ぶ)
- `meme/` — ミーム(確定・修正・削除・引く・抜き出す・要約の取りこぼし)
- `oracle/` — 覚え書き(確定・修正)
- `review/` — ユーザの判断が要るものの一覧(読む専用)
- `fact_check/` — アイデア・oracle・ミームを AI に Dラボのナレッジとネット検索で検めさせ、妥当性と補足を書く(`ai/claude_code/fact_checker.py`)
- `map/` — 星ごとの地図の元データ・svg・距離と方角(入口は `location/list_neighbors.py`)

GUI の API(`gui/api/interface.py`)は、領域のディレクトリ直下のファイルを歩いて、そのファイルで定義した入口のクラスを
「領域.ファイル.クラス」の id で並べる。

- **「作る」と「確定する」を別ファイルに分ける。** 「作る」側(`create_random_*`)は
  db に一切触れず、確定する側の引数のモデルに読み込める形の下書きを返すだけ。db を触るのは「確定する」側だけ
- `run()` が dump した dict を返すのは、Bash 呼び出しをまたいでも(＝プロセスが
  切り替わっても)中身を運べるようにするため。SQLAlchemy のオブジェクトや
  session を返すと、次の呼び出しでは中身が失われる
- 入口の `execute(s)`(`Entrypoint` を直接継ぐ入口は `result()`)はレスポンスのモデルを返し、
  `run()` がそれを dump する。GUI の表の書き込み(`gui/api/records.py`)は `execute(s)` のモデルを直接使う
- 行を id で引くのは `common_query.get_row`(無ければ `UnknownRecordError`。GUI の API は 404 にする)。
  実在レコードを指す欄(id)は、確定する側が呼び出し時に db に居るか確かめる
  (`check_exists`)。スキーマに無い欄は、引数のモデルが読み込むときに止める
- 行をレスポンスのモデルに詰めるのは `record_of(session, モデル, 行)`。当事者・登場人物のような noload のリレーションは、
  モデルの `LOAD_OPTIONS`(`EventRecord` / `EpisodeRecord`)で読み直してから詰める。一覧を引くときは `loading(query, モデル)`
- 行を呼ぶ名前(一覧・参照先・レビュー)は `label.py` の `label_of`
- AI を呼んで得た結果は、得たその場で commit する(長い AI 呼び出しの前も、それまでの保存分を commit する)。
  db だけを触る「確定する」入口は、`execute` の中で commit しない(`.claude/docs/data-access.md`)

入口の基底は `entrypoint.py`(db だけを触る)と `ai_entrypoint.py`(確定のあとに AI を回す)に置く。
読む入口が返す行の組み立ては、各領域の `reading.py` に置く(`event/reading.py` の `EventRow`、`character/reading.py` の `CharacterSheet` など)。

```
Entrypoint(entrypoint.py)
├─ SessionEntrypoint            db セッションを開いて execute(s) へ渡す
│   ├─ CommitEntrypoint         「確定する」系。execute(s) を s.begin() に包む。GUI の API も execute(s) を呼ぶ
│   │   ├─ commit_*.py / update_*.py / delete_*.py / merge_idea.py / set_episode_synced.py
│   │   ├─ idea.resolve_terms.ResolveTerms / idea.link_ideas.LinkIdeas(候補を足す・結ぶので確定側)
│   │   ├─ CommitAndRefresh(ai_entrypoint.py)  確定のあと要約・ミームを作る → CommitEvent / UpdateEvent / CommitStory / CommitEpisode
│   │   └─ CommitMemeSource(ai_entrypoint.py)  確定のあと検めてミームを抜き出す → CommitIdea / CommitOracle
│   ├─ ListEntrypoint           select() の行を row() でモデルにして並べる → list_locations / list_characters / list_character_relations / list_events
│   └─ read_*.py / list_*.py / start_story.py / search_ideas.py / list_pending_reviews.py / draw_memes.py / generate_*.py
└─ RandomDraft                  db に触れない下書き作成 → create_random_*.py
```

(`meme.extract_memes.ExtractMemes`・`meme.refresh_generated_content.RefreshGeneratedContent`・`fact_check.check_facts.CheckFacts` は、
`execute(s)` の外で db セッションを開き直したいので `Entrypoint` を直接継ぎ、`result()` を書く)

### AI を呼ぶ処理と、web のセッションの段

AI を呼ぶ処理は、db だけの関数(対象を引く `*_targets`、材料を組む `*_material`、書き戻す `save_*`)と、
AI だけの関数(`*_draft`。材料のモデルを受けて AI の出力のモデルを返し、db に触らない)に分けて置く。
手元の入口はそれを自分のセッションでつなぐ。Claude Code on the web のセッションは db に繋がないので、
db だけの関数を `<領域>/steps.py` の段(`@db_step`。`step.py`)として API(`POST /api/steps/<領域>.steps.<関数名>`)越しに呼び、
流れは `web_session/` に持つ(`.docs/claude-tasks.md` の「web のセッションで回す」)。

- 段は API の一つのトランザクションで回るので、中で commit しない
- 段の入力・出力は pydantic のモデル。出力は `*Serialized` でない土台のマテリアルで宣言する(列のまま JSON で運ぶ)
- claude を叩く入口を足したら、段と `web_session/` の流れ(`web_session/flows.py` の対応表)も足す

## 引き方は query 側にある

読む側の中身は `data_access_logic/query/` にある。

| モジュール                     | 何のため                                                     |
| ------------------------------ | ------------------------------------------------------------ |
| `common_query.py`              | 時刻の扱い・断面・顔ぶれ・場所の道筋                         |
| `period.py`                    | その時刻に期間(`start` 〜 `end`)が掛かる行の条件(`alive_at`) |
| `character_simulation_query.py` | 人物を軸に周辺を読む(`read_surroundings`)                   |
| `dictionary_query.py`          | アイデア(辞書)の検索。名前・本文(`idea_note` を左外部結合した追記も含む)の部分一致、場所・時刻の範囲、自動生成の候補 |
| `story_creation_query.py`      | 場所に掛かる作品(`story`)の読み出し                          |
| `world_creation_query.py`      | 生きている人物、広さの整合、進行中の判定               |
| `event_seed_query.py`          | 出来事の種をまだ抜き出していない元(`event_seeded` が false) |
| `review_query.py`              | ユーザの判断が要るもの(本文に残った TODO・世界観へ反映していない話) |

入口のファイルはその薄い呼び出し面で、**SQL は組み立てない。**
引く条件は時刻とレコードの id だけで表す。足りない引き方が出てきたら
query 側に関数を足して、ここに入口を一つ被せる。
