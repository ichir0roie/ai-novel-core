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
| `AddTurns` / `AnswerTurn` | `episode_session.form.TurnRequest` / `TurnAnswer` |
| `CommitCharacterLocation` / `UpdateCharacterLocation` | `character.form.CharacterLocationCreateForm` / `CharacterLocationUpdateForm` |
| `CommitCharacterRelation` / `UpdateCharacterRelation` | `character.form.CharacterRelationCreateForm` / `CharacterRelationUpdateForm` |
| `CommitEvent` / `UpdateEvent` | `event.form.EventCreateForm` / `EventUpdateForm` |
| `CommitIdea` / `UpdateIdea` | `idea.form.IdeaCreateForm` / `IdeaUpdateForm`(呼び名の行は `idea.record.IdeaHistoryRow`、その行を知る相手の行は `knowers.KnowerRow`) |
| `CommitMeme` / `UpdateMeme` | `meme.form.MemeCreateForm` / `MemeUpdateForm` |
| `CommitOracle` / `UpdateOracle` | `oracle.form.OracleCreateForm` / `OracleUpdateForm` |
| `CommitStylePreference` / `UpdateStylePreference` | `style_preference.form.StylePreferenceCreateForm` / `StylePreferenceUpdateForm` |
| `UpdateEventSeed` | `event_seed.form.EventSeedUpdateForm` |
| `CommitStory` / `UpdateStory` | `story.form.StoryCreateForm` / `StoryUpdateForm` |
| `CommitEpisode` | `episode.form.EpisodeCommitForm` |
| `GenerateFrame` / `CompletePlot` | `episode.form.EpisodeForm`(下書き。空の欄は指定なし) |
| `GenerateCharacter` | `character.form.CharacterForm`(下書き) |
| `GenerateEvent` | `event.form.EventForm`(下書き) |
| `SearchIdeas` / `ResolveIdeas` | `idea.models.IdeaDraft` のリスト |

(モジュールはどれも `data_access_logic.` を頭に付ける)

`run()` は、入口が組んだレスポンスのモデルを `model_dump(mode="json")` した dict(一覧はそのリスト)を返す。
時刻は `"11579/03/02 00:00:00"` の文字列になる。レスポンスのモデルは、行を写したものが
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
| 「このアイデアは何?」「アイデアを調べて」 | `idea.search_ideas.SearchIdeas(keywords, location_id=None, limit=None, time=None)`。名前・本文(基本の本文と作中の呼び名の両方)の部分一致のあいまい検索。`keywords` は `IdeaDraft(keyword=…, variants=[…])`(`variants` は言い換え)のリスト。当たり方の強い順に返す。中間段が足した候補のアイデアも返す。`location_id` は現在地から最上位までの場所に、`time` はその時刻に効く(`start` <= time < `end`)アイデアに絞る。`called` はその場所・時刻での作中の呼び名 |
| 「この下書きに関わる設定は?」(中間段を自分で回す) | `idea.resolve_ideas.ResolveIdeas(ideas, location_id=None, time=None)`。下書きから洗い出した語(`IdeaDraft`。`keyword` / `variants` / `description` / `kind` / `start` / `end`)をアイデアと照らし、当たったものと上位・下位を返す。当たらなかった語は候補として足す(下の「中間段」)。候補の効く期間は語の `start` / `end`。`start` は `time` と下書きの中身からある程度はっきり言えるときだけ付け(言えなければ省いて None)、`end` は分かるときだけ付ける。`time` は出来事の時刻。`time` を渡すと `start` が空(時期が未定)のアイデアは `ideas` に入れない。呼び名に当たったら本質のアイデアにそろえ、作中の呼び名を `called` に付ける |
| 「この本文が踏まえたアイデアを結んで」 | `idea.link_ideas.LinkIdeas(idea_ids, episode_id)`。話にだけ結ぶ(結んだアイデアが材料の「関係する設定」に出る) |
| 「この候補をあのアイデアにまとめて」 | `idea.merge_idea.MergeIdea(source_id, target_id)`。結んだ本文と source の履歴(呼び名)を付け替えてから source を消す |
| 「判断待ちの一覧」                   | `review.list_pending_reviews.ListPendingReviews()`。未同期の話・本文に残った TODO |
| 「場所を足して」                     | `location.create_random_location.CreateRandomLocation()` で下書き → 内容を決めて `location.commit_location.CommitLocation(location)` |
| 「人物を足して」                     | `character.create_random_character.CreateRandomCharacter()` → `character.commit_character.CommitCharacter(character)`。外見は `appearance`、説明(人物の芯)は `text` に書く。持たせるミームは `meme.draw_memes.DrawMemes(person=True)` で引き、`meme` と `principle`(行動原理)の列に書く(下の「人物が持つミーム」)。来歴の節目は、その年から始まる `histories` の行に一件ずつ書く(下の「人物の来歴」。サブキャラクターは世界の書き進めた所より後を書かない) |
| 「この場所にランダムな人物を何人か作って」「全国家に人物を生成」 | `character.generate_characters.GenerateCharacters(location_ids, time, count=(2, 4), person=True, seed=None)`。場所ごとに `count` の範囲の人数を、時の流れの中で生む人物と同じ自動生成(`data_access_logic/character/generator.py` の `generate_character`。性格・ミーム・来歴・名づけまで AI が決める)で作り、`time` の時点で生まれた歳にする。一人ごとに commit する。場所の種別ごとの人数の上限(下の「世界の広がりと制約」)に達した場所には、上限までしか足さない。作品の無い場所が混ざっていれば作る前に止まる。`person=False` で人物以外の対象を作る |
| 「出来事を足して」                   | `event.create_random_event.CreateRandomEvent()` → `event.commit_event.CommitEvent(event)` |
| 「この下書きから人物を AI に作らせて」 | `character.generate_character.GenerateCharacter(character=CharacterForm(...), time=None, seed=None, plot_text=None)`。欄の値(全部空でもよい)を核に、時の流れの中で生む人物と同じ自動生成(`generate_character`)で全欄を組み立て直して足す。名前・説明は核として渡し、性別・体格・口調・性格・種別・生年・没年・`main_character` は決まった値にする。`time`(現在の時刻)を省けば世界の最新の出来事の時刻。`plot_text` に登場させる話のプロットを渡せば、生年が決まっていなければ、その時刻・場所でその話の役どころ(下書きの説明)を果たせる年齢(0〜90歳。渡さなければ 0〜40歳)にする。説明・来歴には現在の時刻より後のこと(後年の姿・死)を書かず、没年は `main_character` を立てて渡したときだけ持たせる。`character` の `text` と `histories` の各行の説明は、人物像・役どころの下書きとして核にする。`character` に `id` を渡せば(GUI の詳細画面)、その人物の芯(`text`)が空のときに限り、決まっている名前・属性・出自を核に芯と来歴だけを書いて埋める(来歴の節目は今の行に足す。他の欄は変えない) |
| 「この下書きから出来事を AI に作らせて」 | `event.generate_event.GenerateEvent(event=EventForm(...), seed=None)`。名前・記録を場面の指定に、時刻・場所・当事者を決まった値として出来事を一件起こす(下の「出来事の生成」)。時刻を省けば世界の最新、場所を省けば当事者の現在地、当事者を省けばその場所・時刻に居合わせるサブキャラクター。`event` に `id` を渡せば(GUI の詳細画面)、その出来事の本文(`text`)が空のときに限り、名前・場所・当事者から記録の本文だけを書いて埋める(`data_access_logic/event/writer.py`。他の欄は変えない) |
| 「この人物の出自・居場所を足して」   | `character.commit_character_location.CommitCharacterLocation(location)`              |
| 「この二人の相関を足して」           | `character.commit_character_relation.CommitCharacterRelation(relation)`。`text` は時期を限らない関係の芯、関係の中で起きたことは起きた年ごとの `histories` の行に書く(下の「関係の芯と来歴」)。来歴を書き足すときは `UpdateCharacterRelation` に今の行ごと渡す(配列はまるごと置き換わる) |
| 「アイデアを足して」                 | `idea.commit_idea.CommitIdea(idea)`。本体は場所を持たず、効く場所は `histories` の行(非公開の行も含む)の `location_id` で持つ(行の無いアイデアはどこでも効く)。効く期間は本体の `start` / `end`(出来事の時刻と比べる。空なら限らない)。`parent_idea_id` を渡さなければ、`kind` の分類アイデア(下の「アイデアの分類」)を、場所のある最初の行の `location_id` から自動で探して親にする(無ければ作る)。場所・時代ごとの作中の呼び名は `histories`(下の「アイデアの履歴(呼び名)」)。本文は作者だけが読むので、確定のあとに AI(事実確認・ミームの抜き出し)を回さない。確定したアイデアを返す |
| 「作中での呼び名を足して」「この場所・時代では〇〇と呼ぶ」 | `idea.commit_idea.CommitIdea(idea)` / `idea.update_idea.UpdateIdea(idea)` に `histories`(下の「アイデアの履歴(呼び名)」)を付けて足す。呼び名を使う場所・時代は各行の `location_id` / `start` / `end`(空の列はどこでも・いつでも) |
| 「oracle・ミームを検めて」「妥当性を調べて」 | `fact_check.check_facts.CheckFacts(table, ids=None, limit=None)`。`table` は `"oracle"` / `"meme"`(アイデアの本文は作者だけが読むので検めない)。AI が Dラボのナレッジ(優先)とネット検索で妥当性と補足を書き、本文の末尾の `# 検証結果` の節に入れる(前の節は置き換える)。`ids` を省くとまだその節の無いものすべて(`limit` で件数を絞る)、渡すと検め済みでも検め直す。oracle は検めたあと、その節を含む本文からミームを抜き出し直し、足したミームも検める。`{"checked", "memes_added"}` を返す |
| 「場所を直して」                     | `location.update_location.UpdateLocation(location)`                                 |
| 「この人物の〇歳からの名字・背丈・口調・性格を決めて」「結婚して名字が変わる」 | `character.update_character.UpdateCharacter(CharacterUpdateForm(id=…, parameters=[...]))`。変わった時ごとの行の配列をまるごと渡す(下の「変わった時ごとのパラメータ」)。今の配列は `ReadCharacter` の `parameters` で読める |
| 「この人物の来歴を足して」「この人物の説明の移り変わりを足して」「〇年からの立場を記録して」「年の決まっていない構想を足して」 | `character.update_character.UpdateCharacter(CharacterUpdateForm(id=…, histories=[...]))`。起きた年ごとの行の配列をまるごと渡す(今の配列は `ReadCharacter` の `histories` で読む。時刻を渡すとその時刻までの行だけになるので、書き足すときは時刻を渡さずに読む)。年の決まっていない構想は `start` を空にした行に書く。下の「人物の芯と来歴」 |
| 「人物を直して」                     | `character.update_character.UpdateCharacter(character)`。名字・体格・口調・性格は `parameters` に、外見は `appearance`、芯は `text`、ミームは `meme`、行動原理は `principle`、筋書きは `plot` に、来歴は `histories` に、本文を知る相手は `knowers` に入れる(渡さなければ触らない)。出自・居場所は `character.update_character_location.UpdateCharacterLocation(location)`、相関は `character.update_character_relation.UpdateCharacterRelation(relation)` |
| 「場所を消して」                     | `location.delete_location.DeleteLocation(location_id)`                              |
| 「出来事を直して」                   | `event.update_event.UpdateEvent(event)`。`id` 必須、渡した欄だけ直す。`character_ids` を渡すと当事者をまるごと置き換える。直したあと要約(`event_summary`)を作り直す |
| 「出来事を消して」「出来事を作り直して」 | `event.delete_event.DeleteEvent(event_id)`。子の出来事が残っていれば止まる。当事者・アイデアとの中間テーブルの行と要約も消す。出来事で人物の `histories` に積み足した行と、足したアイデアの候補は残るので、要らなければ `UpdateCharacter` / `DeleteIdea` で別に戻す |
| 「アイデアを直して」                 | `idea.update_idea.UpdateIdea(idea)`。`id` 必須、渡した欄だけ直す。`histories` を渡すと配列をまるごと置き換える(下の「アイデアの履歴(呼び名)」) |
| 「アイデアを消して」                 | `idea.delete_idea.DeleteIdea(idea_id)`。下位のアイデアが残っていれば止まる。結んだ本文との中間テーブルの行、履歴(呼び名)の行も消す |
| 「覚え書きを足して」「oracle に書いて」 | `oracle.commit_oracle.CommitOracle(oracle, fact_check=True)`。`text` 必須。題は `title`。確定したあとは、検めて(`fact_check`。本文の末尾に `# 検証結果` の節を足す)、その節を含む本文からミームを抜き出し(`memes_added`)、足したミームも検める |
| 「覚え書きを直して」                 | `oracle.update_oracle.UpdateOracle(oracle)`。`id` 必須、渡した欄だけ直す |
| 「ミームを足して」「この考え方をミームに入れて」 | `meme.commit_meme.CommitMeme(meme)`。`text` 必須。`category` は 信条/欲求/境遇/集団/理 のいずれか(空でもよい。次の抽出で AI が振る)。置き場所は分類のディレクトリ |
| 「ミームを直して」「ミームの分類を直して」 | `meme.update_meme.UpdateMeme(meme)`。`id` 必須、渡した欄だけ直す。`category` は 信条/欲求/境遇/集団/理 のいずれか |
| 「ミームを消して」                   | `meme.delete_meme.DeleteMeme(meme_ids)`。id の配列をまとめて一つのトランザクションで消す(一つでも無ければ何も消さない)。GUI のミームの一覧で選んで消すのもこれ |
| 「出来事の種を直して」               | `event_seed.update_event_seed.UpdateEventSeed(seed)`。`id` 必須、渡した欄だけ直す。語の置き換えなどは db を読んで id を拾ってから呼ぶ |
| 「ミームを抜き出して」               | `meme.extract_memes.ExtractMemes()`。oracle(著者の覚え書き)の本文(`# 検証結果` の節を含む)・出来事の本文・話の本文(`main_text`)から抜き出し(アイデアの本文と人物の筋書きからは抜き出さない)、分類を振って `meme` テーブルへ足す。既にあるミームと同じ考え方の言い換えは足さない。最後に、分類の空いたミーム(手で足したものなど)に分類を振る。足したミームは AI が Dラボのナレッジとネット検索で検め、本文の末尾の `# 検証結果` の節に書く(`ExtractMemes(fact_check=False)` で飛ばす。重複の確かめ・分類・人物へ引くときは、この節を除いた文面を使う)。足した件数を `{"memes_added"}` で返す。承認の段は無く、分類の付いたミームは足したその時から `DrawMemes` で人物へ引かれる |
| 「ミームを引いて」                   | `meme.draw_memes.DrawMemes(person=True, seed=None)`。ミームから、分類ごとに 0〜2 件引き、それぞれに古今表裏を割り振って返す。db には書かない |
| 「ミームと要約の取りこぼしをまとめて作って」 | `meme.refresh_generated_content.RefreshGeneratedContent()`。`ExtractMemes` に加えて、要約が無いか本文と食い違っている出来事・話をすべて拾って `event_summary` と話の `summary_text` を作り直す(数は作り直した件数)。`CommitEvent` / `CommitStory` / `CommitEpisode` は確定した一件だけを見るので、GUI から直した分などの取りこぼしを拾うのはこちら |
| 「作品の一覧」                       | `story.list_stories.ListStories()`                                           |
| 「話を書き始める」「次の話を書く」   | `story.start_story.StartStory(story_id, time=None)`。同期確認・見出し・直前の話・断面・顔ぶれを一度に出す。`time` を省けば作品の最後の話の時刻 |
| 「前の話を読ませて」                 | `episode.read_episodes.ReadEpisodes(story_id, count=10, before=None, text=True)`。`before` は時刻で、start がそれより前の話に絞る |
| 「その時点の顔ぶれは?」             | `story.read_cast.ReadCast(story_id, time=None)`。`time` を省けば作品の最後の話の時刻 |
| 「その場所・その時点の様子は?」     | `story.read_brief.ReadBrief(location_id, time)`                                 |
| 「この人物の周りで何が起きている?」 | `character.read_surroundings.ReadSurroundings(character_id, time)`               |
| 「この人物がその時に知っていることを読ませて」 | `character.read_knowledge.ReadKnowledge(episode_id, character_id)`。人物役が、話のセッションでいる時刻(その人物の一番新しい手番の行の `time`、無ければ話の時刻)に知ることのできるデータ。時刻・年は渡さず、来歴の年はその時刻から何年前か(「今年」「13年前」)で出す。本人の外見・芯・ミーム・行動原理・その時の名字や口調、その時刻に関係のある人物の外見と芯、本人と関係のある人物の来歴、その時刻に続いている関係(芯と、時刻の年までに起きた来歴)、知っているアイデア(住む場所に効くものと、知る相手に入ったもの)の本文と来歴を返す。芯・来歴は知る相手に当たるものだけ。来歴は時刻の年までに起きた行だけ。筋書き(`plot`)は出さない(下の「本文・来歴を知る相手」) |
| 「初対面の相手の見た目を読ませて」 | `character.read_appearance.ReadAppearance(character_id, time)`。会った相手から見て分かること(種別・歳・性別・背丈・体格・外見)。名前は出さない。語り部が初対面の人物の状況の差分を書くときに使う |
| 「話のセッションに手番を足して」「人物役の一手を待って」 | スキル `episode` の「語り部と人物役」。表(`episode_character_session`)は `tool.episode_session` のコマンドで扱う。入口は `episode_session.add_turns.AddTurns(episode_id, turns)`(語り部が要求の行を足す)・`answer_turn.AnswerTurn(record_id, answer)`(人物役が番の行に一手を入れる)・`read_turn.ReadTurn(episode_id, character_id)`(人物役の番か: turn / waiting / closed。番の行は要求と終了の印だけで、時刻は返さない)・`read_session.ReadSession(episode_id)`(すべての行)・`read_stage.ReadStage(episode_id)`(語り部が読む材料。プロット・時刻・場所・登場人物の外見と芯と来歴・登場人物どうしの関係とその来歴・話に結んだ設定の本文と履歴。芯・来歴・履歴は知る相手に関わらずすべて渡し、非公開かどうかと知る相手を添える。前の話・本文は入らない)・`close_session.CloseSession(episode_id)`(出た人物に終了の行)・`clear_session.ClearSession(episode_id)`(その話の行をすべて消す。演じ直す前に)。行動の入っていない一番古い行の人物が、いま動く番 |
| 「この人物を本文用にそろえて」       | `character.read_character.ReadCharacter(character_id, time=None)`。体格・口調・性格は `time` の時点の値を上の段に出す(`time` を省くと生まれたときの値)。変わった時ごとの行は `parameters`。芯は `text`。来歴(`histories`)は `time` の年までに起きた行だけを古い順に出す(`time` を省くと、年の決まっていない行も最後に含めてすべて) |
| 「作品を作る」「筋書きを足して」     | `story.commit_story.CommitStory(story)`。筋書きは作品の `text` に書く        |
| 「この作品の子に章・外伝を作って」   | `story.commit_story.CommitStory(StoryCreateForm(name=…, parent_story_id=<親の作品id>, …))`。付け替えは `UpdateStory(StoryUpdateForm(id=…, parent_story_id=…))`(自分か子孫の子にはできない。`None` を渡せば親から外す)。子の作品の話を書くときは、親をたどった作品の筋書き(`親の作品`)を渡す。前の話・文体の見本の範囲は下の「出来事の生成・話の材料」の「前の話は」の段落 |
| 「作品を直して」「筋書きを直して」   | `story.update_story.UpdateStory(story)`                                      |
| 「作品を消して」                     | `story.delete_story.DeleteStory(story_id)`。話か子の作品が残っていれば止まる |
| 「この下書きから話の枠を AI に決めさせて」 | `episode.generate_frame.GenerateFrame(frame=EpisodeForm(story_id=…, viewpoint_character_id=…, location_id=…, character_ids=[…], …))`。下書きを枠として保存してから、題・プロット(`ai/instructions/plot.py` の形)・時刻を下書きを核に AI が決める(`id` を渡せばその本文の無い枠を決め直す。本文のある話は保存の前に止まる)。時刻は下書きにあればそれ、無ければ直前の話の後から AI が選ぶ。視点(`viewpoint_character_id`。Character への FK)・場所(`location_id`。Location への FK)は AI には決めさせず、下書きにあればその id をそのまま使う(無ければ NULL のまま)。登場人物は下書きの `character_ids`(省けば枠の `episode_character`)で、足した枠の `episode_character` にも残す。書き直したプロットに名前が出る既存の人物は `mentioned` の行として登録し(下の「名前だけ出る人物」)、その設定を AI に渡す |
| 「プロットを補完して」「プロットを場面まで書き直して」「足りない人物・舞台を作って」 | `episode.complete_plot.CompletePlot(episode=EpisodeForm(story_id=…, character_ids=[…], …), order=None, model=None, effort=None)`。プロット補完。今のプロット(`plot_text`)を核に、`order`(作者の注文。展開・焦点・雰囲気など)も取り入れて、本文全体を場面に割ったプロット(`ai/instructions/plot.py` の形)を AI に書き直させ、それでプロットをそっくり置き換える(今のプロットの中身は書き直したプロットに含めさせる。本文は書かない)。書き直したプロットに出るのに登場人物にいない人物は `generate_character` で作り(プロットが固有の名で呼ぶときだけその名を核にし、役職・あだ名は説明に添える)、話の `episode_character` に足す。書き直したプロットの主な舞台が話の場所(無ければ作品の立つ場所)より細かく、その直下の既知の場所にも無ければ、その場所の下に作って話の `location_id` にする。プロットか時刻が空なら先に `GenerateFrame` と同じ生成で枠を決める。登場人物は下書きの `character_ids`(話の `episode_character` と同じ欄)、省けば枠の `episode_character` で、空なら枠を決める前に止まる。`model` / `effort` はプロットの書き直しと候補の呼び出しにだけ効く(省けば AI の client の既定)。書き直したプロットに名前が出る既存の人物は `mentioned` の行として登録し(下の「名前だけ出る人物」)、その設定を AI に渡す |
| 「この話を推敲して」「初登場キャラの描写を厚くして」 | スキル `revise-episode`。このセッションの Claude が `ReadEpisodeBrief` で材料を読んで自分で書き直し、`CommitEpisode` で確定する(`synced` はそのまま渡し、指示はプロットの「## 推敲」の節に積む。登場人物・場所が変わるなら、書く前に `CastEpisode` で結び直して材料を読み直す) |
| 「本文を確定する」「話のプロットを入れる」 | `episode.commit_episode.CommitEpisode(episode)`。`id` を渡せばその話を直し(渡した欄だけ)、省けば `story_id` の作品に新しい話を足す。`synced` を渡さなければ同期していない扱い(false)にする。`plot_text`(プロット)か `main_text`(本文)のどちらかがあればよい。`main_text` は `ai/instructions/style.py` の `layout_novel_text` で改行を整えてから入れる(地の文は一文一行、「◇」の行は空行二つ)。話に番号は無く、作品の中では `start` の順に並ぶ(`start` の無い話は後ろに id 順)。あいだに話を足すときは、前後の話のあいだの `start` を付ける |
| 「未同期の話は残ってる?」           | `episode.list_unsynced_episodes.ListUnsyncedEpisodes(story_id=None)`           |
| 「話を別の作品(章)へ移して」       | `episode.move_episodes.MoveEpisodes(episode_ids, story_id)`。話の作品を付け替える。本文・要約・同期フラグはそのまま |
| 「話を消して」                       | `episode.delete_episode.DeleteEpisode(episode_id)`。登場人物・踏まえたアイデアとの中間テーブルの行も消す。本文から足した出来事・アイデアの候補・ミームは残るので、要らなければ別に消す |
| 「世界観へ反映済みにする」           | `episode.set_episode_synced.SetEpisodeSynced(episode_id, synced=True)`   |
| 「話の要約を作り直して」「要約がおかしい」 | `episode.rewrite_episode_summary.RewriteEpisodeSummary(episode_ids)`。本文が変わっていなくても、話の概要(`episode.summary_text`)を AI に作り直させ、一件ごとに commit する。本文が変わったときの作り直しは `CommitEpisode` などが自動で行うので、これは中身の崩れた要約を直すとき用 |
| 「この場所・この時の出来事を起こして」「ヴァレンツァで11579/03/02に〇〇な場面」 | `event.generate_event.GenerateEvent(event=EventForm(location_id=…, time=…, name="〇〇な場面"))`。当事者はその時刻にそこにいて手の空いたサブキャラクターから選ぶ(下の「出来事の生成」)。当事者を決めるなら `character_ids` |
| 「このプロットで話を書いて」「〇〇と△△が出る話を 11579/03/02 で」「この枠に本文を書いて」 | スキル `episode`。このセッションの Claude が `ReadEpisodeCasting` でプロットから登場人物・場所を推測して `CastEpisode` で結び、プロットの語を `ResolveIdeas` でアイデアと照らして `LinkIdeas` で結び、そのあと材料を `ReadEpisodeBrief` で読んで自分で本文を書き、`CommitEpisode`(`synced=True`)で確定する(新しい話は先に `CommitEpisode` で枠を足す) |
| 「この話の登場人物・場所を決める材料を読ませて」 | `episode.read_episode_casting.ReadEpisodeCasting(episode_id)`。この話(題・時刻・場所・視点・プロット)・今の登場人物・名前だけ出る人物・登場人物の候補(登場人物と関係のある人物・話の場所にいる人物。プロット・本文に名前が出る人物は「名前だけ出る人物」に出る)・話の場所の中の既知の場所と、登場人物・名前だけ出る人物それぞれがこの話より前に関わったすべての話(作品を問わない。概要つき)を、日本語の見出しと id 付きで返す。関わった話の概要が無いか本文と食い違っていれば、読む前に AI で作り直す(作れなかった話は null)。時刻が空なら止まる |
| 「人物を消して」 | `character.delete_character.DeleteCharacter(character_id)`。期間ごとの値・説明の変化・出自と居場所・相関・話に名前だけ出る行も消す。出来事の当事者か、話の登場人物・視点になっている人物は止まる |
| 「この話を id で読ませて」「人物が関わった話の本文を読みたい」 | `episode.read_episode_texts.ReadEpisodeTexts(episode_ids)`。作品・題・時刻・プロット・本文・概要を時刻の順に返す |
| 「名前だけ出る人物を拾い直して」 | `episode.refresh_mentions.RefreshMentions(episode_ids=None)`。今のプロット・本文から `episode_character` の `mentioned` の行を拾い直す(省けばすべての話)。拾い直しは保存のときにしか走らないので、古い話やあとから人物を足した話の取りこぼしを埋める。登場人物の行は変えない |
| 「この話の登場人物・場所を結んで」 | `episode.cast_episode.CastEpisode(episode_id, character_ids, location_id=None, viewpoint_character_id=None)`。登場人物(`episode_character`)をまるごと置き換え、名前だけ出る人物を拾い直す。場所・視点は渡したときだけ書く。同期フラグは変えない |
| 「この話を書く材料を読ませて」 | `episode.read_episode_brief.ReadEpisodeBrief(episode_id)`。書き方(文体の決まりと `style_preference` の `shared` / `episode` の行)・作品・前の話の概要(この話より前の、同じ作品のすべての話と登場人物が関わったすべての話)・文体の見本(同じ作品・章・外伝の直前の五話の本文。中身は読ませない)・この話(題・時刻・同期・場所・視点・登場人物・名前だけ出る人物・関係・関係する設定・プロット・今の本文)・場所の直近の出来事・後に決まっている出来事を、日本語の見出しと id 付きで返す。登場人物の直近の出来事・関係と場所の出来事は話に結んだ登場人物・場所から、関係する設定は話に結んだアイデア(`episode_idea`)から引く(結んだ人物と同じく効く期間では絞らず、呼び名はアイデアの履歴 `idea_history` のうち話の時刻・場所に効くもの)ので、先に `CastEpisode` / `LinkIdeas` で結んでから読む。時刻が空なら止まる。前の話・出来事の要約が本文と食い違っていれば、読む前に AI で作り直す(本文は書かない) |

筋書きのテーブルは無い。場所に掛かる筋書きは作品(`story`)の
`text` に、人物に掛かる筋書きはその人物の `plot` に書く。

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

**人物の本文と来歴(appearance・text・meme・principle・plot / character_history)**: 人物の本文は列に分けて持つ。
外見(`appearance`。見て分かること)、芯(`text`。経歴・立場・性格の説明)、ミーム(`meme`)、行動原理(`principle`)、
筋書き(`plot`。作者がその人物について進めたい先の筋)。どれも時期を限らない説明で、作者の目で書く材料(話・出来事・人物の生成)にはいつも渡る。時が進むにつれて起きたこと・変わった立場・境遇などの来歴は、
`character_history` テーブルに起きた年ごとの行(`start` / `description`)で積む。入口では人物の
`histories` に配列で並ぶ(id と character_id は出さない。行は配列の並びで決まり、並びを変えなければ id も変わらない)。
アイデアの履歴(`idea_history`)と同じく子の配列 `histories` で持ち、GUI の見た目も揃えている。

```json
"appearance": "煤けた腕の太い男。…",
"text": "村の鍛冶屋。…",
"meme": "- 古表: …",
"principle": "…",
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
- 口調・話し方は芯にも来歴にも書かず、パラメータの `tone`(語尾・訛りは `dialect`)に、変わった時ごとの行で書く。`tone` は後の行が前の行を丸ごと上書きするので、時期を問わない癖は `tone` を持つ各行に入れる
- 話・出来事・人物の生成に渡す材料は、本文の列(外見・人物像・ミーム・行動原理・筋書き)と、その時刻の年までに起きた行(`start` <= 時刻の年)だけを古い順に並べた来歴
  (`data_access_logic/character/histories.py` の `histories_at`)。先の年から始まる行や年の決まっていない行を書き足しても、それより前の話・出来事には効かない
- 来歴を書き足すときは、既にある説明を書き換えず、起きた年の行があればその説明の末尾に足し、無ければその年を `start` にした行を足す
  (`UpdateCharacter` は配列をまるごと置き換えるので、時刻を渡さない `ReadCharacter` で今の行をすべて読み、足した配列を渡す)
- `CommitCharacter` / `UpdateCharacter` は本文の列と `histories` を受け取る。`UpdateCharacter` に `histories` を渡すと配列をまるごと置き換える
- 出来事の生成(`GenerateEvent` など)で人物について分かったことは、出来事の年の行に足す(`add_history`)

**アイデアの履歴(呼び名)**: アイデアの本文(`text`)は本質で、作者(語り部と、話を書くセッションの Claude)だけが読む。人物役にも、AI の生成(人物・出来事・話の枠・プロット補完)にも渡さず、生成には呼び名と受け止め方だけを渡す(`idea/models.py` の `idea_for_prompt`)。
作中の人物が知ること(本質の `name` とは別に、この場所・この時代ではこう呼び、こう受け止めている、ということ)は、
`idea_history` テーブルに場所・時代ごとの行(`location_id` / `start` / `end` / `name` / `detail`)で積む。
`detail` には、作中の人がそのアイデアについて知っていること・信じていることを、作中の言葉で書く。入口ではアイデアの `histories` に配列で並ぶ(id と idea_id は出さない。行は配列の並びで決まり、
並びを変えなければ id も変わらない)。

```json
"histories": [
  {"location_id": 12, "start": null, "end": "11700", "name": "魔力", "detail": "住人は魔法の力だと思っている"},
  {"location_id": null, "start": null, "end": null, "name": "力", "detail": null}
]
```

- `location_id` は効く場所(その場所と配下で効く)、`start` / `end` は効く期間。どちらも空ならどこでも・いつでも効く
- アイデアの本体は場所を持たない。アイデアが効く場所は、この行(非公開の行も含む)の場所・期間で決まる(`dictionary_query.idea_in_scope`)。行の無いアイデアはどこでも効き、行があれば、場所・期間の当たる行が一つでもあれば効く
- `name` は必須。その場所・時代でアイデアをこう呼ぶ、という作中の呼び名
- `detail` は呼び名についての注釈(作中でどう受け止められているか)。無くてもよい
- `private` を true にした行は非公開。効く場所・期間に住む人物も知らず、知る相手(`knowers`)だけが知る。作中の呼び名(`called`)にも使わない
- `CommitIdea` / `UpdateIdea` は `histories` を受け取る。`UpdateIdea` に渡すと配列をまるごと置き換える
- `SearchIdeas` の名前・本文検索、`data_access_logic/idea/search.py`、`data_access_logic/idea/context.py`(中間段)、清書に渡す「関係する設定」
  (`IdeaContextSerialized`)は、いずれもアイデアの `histories` を見て、当てはまる場所・時代の
  履歴があればその `name` で呼び、`detail` を「作中での受け止め方」として添える。当てはまる履歴が無ければ本質の `name` をそのまま使う
- ある場所・時代の履歴(呼び名)がある行は、清書のプロンプト(`ai/instructions/idea_context.py`)で
  「その場所・時代の人物はこの名前を認識しているもの」として扱われ、本文ではその名で呼ぶ
- `MergeIdea` は `source_id` の `histories` を `target_id` へ付け替えてから `source_id` を消す。
  `DeleteIdea` は下位のアイデアが残っていなければそのまま消し、`histories` も一緒に消える

**本文・来歴を知る相手**: 人物の本文と来歴の行、アイデアの履歴の行は、知る相手の表(`character_knower` /
`character_history_knower` / `idea_history_knower`)の行に当たる人物が知る。人物の来歴とアイデアの履歴の行は同じ形で、
公開の行は知る相手のほかにも知る人物がおり、非公開(`private`)の行は知る相手だけが知る。
アイデアの本文は誰も知らない(作者だけが読む)。

- 知る相手の行は、知る人物(`knower_id`)か知る場所(`location_id`)のどちらか一方と、知った時刻(`start`。空なら初めから)を持つ
- 場所の行は、その時刻にその場所(配下も含む)に住む人物(`character_location`)が知る。誰もが知ることは世界の場所で表す
- 人物の来歴の公開の行は、本人とその時刻に関係(`character_relation`)のある人物も、知る相手の行が無くても知る。
  非公開(`private`)の行は知る相手だけが知る
- アイデアの履歴の公開の行は、行の効く場所(`location_id`。空ならどこでも)と期間に住む人物も、知る相手の行が無くても知る。
  非公開(`private`)の行は、場所・期間に関わらず知る相手だけが知る
  履歴の行の無いアイデアは、人物役のだれも知らない
- 入口では人物の本体と来歴の行、アイデアの履歴の行の `knowers`(行の配列)で出し入れする。渡すとまるごと置き換える
- 人物は、作るとき本人が自分の本文を知る相手に入る(`db/schema.py` の `_knows_oneself`。`CommitCharacter` の `knowers` は本人のほかの相手)
- 来歴・履歴の行で `knowers` を渡さない行は、今ある行なら知る相手をそのままにし、新しい行なら人物の来歴は本人だけ、アイデアの履歴は行の無いまま
  (`db/child_lists.py` の `replaced_histories`)。`private` を渡さない行は公開になる(今ある行を渡し直すときも、読んだ `private` を渡す)
- 本人も知らない来歴(記憶を失った人物・出生の秘密など)は、非公開にして知る相手から本人を外す。本人も知らない本文は、知る相手から本人を外す
- 知る相手で絞るのは、人物が知ることのできるデータ(`ReadKnowledge`。スキル `episode` の人物役が読む)だけ。
  人物役には、本人の外見・芯・ミーム・行動原理と、関係のある人物の外見と芯(知っていれば)を渡し、筋書き(`plot`)はだれにも渡さない。
  話・出来事・人物の生成と、本文を書く Claude・語り部が読む材料(`ReadEpisodeBrief`・`ReadStage` など)は作者の目で書くので、知る相手に関わらずすべてを渡す
- 本文を書く Claude・語り部が読む材料(`ReadEpisodeBrief`・`ReadStage`)は、人物の芯に知る相手を、人物の来歴とアイデアの履歴の行に
  非公開かどうかと知る相手を添える(`character.cast.secrets_at`・`idea.links.linked_ideas_at`)。知る相手は話の時刻までに知った相手だけ、
  来歴・履歴は話の時刻までに始まった行だけ(アイデアの履歴は効く場所・終わりを問わない)
- `add_history`(出来事・人物の生成が来歴に書き足す)と、人物の生成が書く来歴の節目は、AI の書いたことに秘密が混じりうるので、
  本人だけが知る非公開の行にする(その年の本人だけが知る非公開の行があれば、そこに書き足す)

**アイデアの分類(親の自動探索)**: `parent_idea_id`(上位のアイデア)は、`kind` ごとに一つ、その kind を
まとめる「分類」のアイデア(`name` が `kind` と同じ。例: `name="組織" kind="組織"`)を親にしてぶら下げる。
`CommitIdea` に `parent_idea_id` を渡さなければ(中間段(下の「中間段」)が候補を足すときも同様)、
`data_access_logic/idea/classification.py` の `find_or_create_classification` が、場所のある最初の履歴の行の `location_id` の場所チェーンを
根まで遡り、その場所に履歴の行を持つ、同じ種別のアイデア(たいていは「星」のアイデア)が見つかった一番深いところを探して、その子から
`kind` の分類を探す。あれば再利用し、無ければ `name=kind` の分類を、その場所の非公開の行を付けて新しく作って親にする。
場所チェーンのどこにも対応するアイデアが無ければ親を決めようがないので、`parent_idea_id` は空のまま
(明示的に渡した `parent_idea_id` はそのまま尊重し、自動探索はしない。分類自体を足すとき(`name == kind`)も、
自分自身の親を探しに行かない)。

人物の来歴は、節目の年を `start` にした `histories` の行に、
`<何があり、立場・仕事・住まい・人間関係がどう変わったか>` を `description` として書く(同じ年の節目は一行にまとめる)。人物説明にある立場・仕事・住まいには、いつそうなったかの節目を必ず入れる。
「現在」の行は要らない。話・出来事の材料にはその時刻までに始まった節目だけが渡るので、後年の立場を先取りしない。

サブキャラクター(`main_character` が false の人物・対象)の `histories` には、世界の書き進めた所(本文のある話の一番新しい `start`)より後のこと
(後年の立場・死・「# 未来」の節・`plot` の先の筋・その時より後に始まる行など)を書かない。没年(`end`)と、居場所(`character_location`)の境目より後の始まり・終わりも入れない。出来事の生成はサブキャラクターを当事者に選ぶので、
決まった未来があると、生成した出来事や進めたメインの出来事と食い違いやすくなるため。来歴は話の本文で起きたことを、
話を確定するたびに足していく(スキル `episode` の「確定のあと」)。人物の自動生成(`generator.py`)も、説明・来歴に現在の時刻より後のことを書かせず、サブキャラクターには没年を持たせない。プロット補完で作る人物には話のプロットを渡し、その役どころに合う年齢にする。主要人物(`main_character` が true)は、作者の構想として未来まで書いてよい。未来の節目は、その年を `start` にした行にすれば、それより前の話・出来事には渡らない。年がまだ決まっていない構想は `start` を空にした行に書けば、どの話・出来事にも渡らない。筋書き(`plot`)はいつの話・出来事にも渡るので、先の筋を前の話に見せたくなければ、来歴の行に書く。

**関係の芯と来歴**: 関係(`character_relation`)の `text` は、どういう間柄かという時期を限らない芯だけを書く。
関係の中で起きたこと・変わったことは、人物の来歴と同じく、起きた年を `start` にした `histories` の行(`character_relation_history`)に書く。
話の材料・人物役には、その時刻に続いている関係(`start` 〜 `end`)の、時刻の年までに起きた行だけが渡る(`character/cast.py` の `relations_at`)。
後年のこと(看取る・別れる・最期など)を `text` に書くと、それより前の話・人物役にも渡ってしまうので、その年の行に書く。年の決まっていない構想は `start` を空にした行に書く。
間柄そのものが変わる(師弟から仲間へ、など)ときは、来歴の行ではなく、`end` で区切った新しい関係の行にする。

人物が持つミーム(行動原理の芯。`meme` テーブル)は、その人物の `meme` 列に、持つミームの文面を
`- <古今表裏>: <文面>` の箇条書きでそのまま書く。人物は複数のミームを持ってよい。ミームどうしの関係の整理は、
`meme` ではなく `principle`(行動原理)に書く。

- 古今表裏: 古=かつて持っていたが今は手放した / 今=いま持っている / 表=人前で掲げている / 裏=内に秘めている
- 引き方: 分類ごとに 0〜2 件。人物は 信条・欲求・境遇、人物以外の対象は 信条・欲求・集団 から引く。
  理(世界の法則)は引かない(`data_access_logic/constants.py` の `MEME_*`)
- 人物の自動生成(`data_access_logic/character/generator.py`)は、この引き方と整理を自動で行う

## 世界の広がりと制約

承認の段は置かない。生んだ人物・出来事・アイデア・ミームは、足したその時から検索・生成・話の材料に出て、世界は作者の手を離れて広がっていく。
その代わり、崩れないよう、人物の自動生成(`data_access_logic/character/generator.py`)は足す前に次の構造と制約を通す。

- 居場所: 生成した場所を、その一件の居場所(`character_location`)として生まれた時から今まで続く行で足す。中身を決める AI には、
  今の住まい・仕事場もその場所(かその中)に置かせる(筋書きが別の場所の役どころを示していても、その場所で担う形に移させる)
- 世界との検め(`consistency.py`): 中身の説明・行動原理・来歴を、居場所・現在の時刻・まだ無い設定・説明の語に当たった設定(中間段)・既にいる人物や対象と照らして
  一回の AI 呼び出しで検めさせ、食い違いがあればそこだけ直させる(直した食い違いはログに出す)
- 名付け(`naming.py`): 居場所と中身から名前の候補を `NAME_CANDIDATE_COUNT`(10)個 AI に出させ、同じ場所(居場所とその上位・配下)に
  いる人物・対象と同じ名を除いて、サイコロで一つ選ぶ。作者が名を指定したときは、その名(か近い響き)をそのまま使う
- 人数の上限: ランダムに人物を足す `GenerateCharacters` は、場所にじかにいる人物・対象を種別ごとの上限
  (`constants.RESIDENT_LIMITS`。無い種別は `DEFAULT_RESIDENT_LIMIT`)までしか足さない。話の役どころから作る人物は限らない

## 中間段(下書き → 語の洗い出し → 清書)

本文を書く生成は、下書き(一段目)と清書(二段目)のあいだに、アイデアと照らす中間段を挟む
(`data_access_logic/idea/context.py`)。

1. 下書きから、設定資料と照らす語とその言い換えを AI に挙げさせる(`data_access_logic/idea/search.py` の `keywords_of`)。
   出来事の時刻と下書きの中身から、語ごとの `start` / `end` も決めさせる。ある程度はっきりした `start` が言えない語は null、`end` は分かる語だけ
2. 語と言い換えで、アイデアの名前・本文(場所・時代ごとの作中の呼び名 `idea_history` の `name` / `detail` も含む)を
   部分一致で引く(`data_access_logic/idea/search.py` の `search`)。その場所・時刻で効くアイデアだけ。
   場所は、アイデアの履歴の行(非公開も含む)の `location_id` が現在地から最上位までの場所のどれかに当たるもの(行の無いアイデアはどこでも)。
   時刻は、出来事の時刻が `start` 以上 `end` 未満のもの(`end` が空なら限らない)。
   `start` が空のアイデアは時期が未定で、その時刻にもうあるかが分からないので、語が当たっても清書に渡さない(候補も足さない)。
   当たったアイデアに上位・下位のアイデアを足して、清書に「関係する設定」として渡す
3. どのアイデアにも当たらなかった語は、AI が決めた種別(`kind`)で足す(同じ名前のアイデアが場所・時刻の外にあれば、足さずにそれを結ぶ)。
   場所は世界線(非公開の履歴の行で持つ)、`start` / `end` は 1. で決めたもの(null ならそのまま空。時期が未定の候補になる)。親(`parent_idea_id`)は
   上の「アイデアの分類(親の自動探索)」の通り自動で決める。足した候補は、次からの検索・断面・清書に他のアイデアと同じく出る
4. 話の本文なら、下書きが当たったアイデアと候補を中間テーブル(`episode_idea`)で話に結ぶ(人物・出来事には結ばない)

| 生成 | 下書き | 清書 |
| ---- | ------ | ---- |
| 人物の自動生成 | 中身を決めた説明 | 世界との検め(`consistency.py`)で、関係する設定と合わせて直す |
| プロット補完(`data_access_logic/episode/plot_completer.py`) | 今のプロット(`plot_text`) | 書き直したプロット |

claude が対話で書くときは、自分で語と言い換えを挙げて `ResolveIdeas` を呼び、返った `ideas` を踏まえて書く。
話の本文(スキル `episode` / `revise-episode`)だけは、プロットの語で `ResolveIdeas` を呼んで踏まえるアイデアを書く前に `LinkIdeas` で話に結び、
`ReadEpisodeBrief` の「関係する設定」(結んだアイデア)を読んでから本文を書く。

`meme` テーブル自体は oracle・出来事・話の本文から抜き出して貯めるだけで、
人物との FK は持たない(ミームは人物の間を移り変わり・伝染していくため)。

補足:

- `CommitEvent` / `UpdateEvent` / `CommitEpisode` は、確定したあとに毎回(`run()`。流れは `flows/commit.py`)
  ミームの棚卸し
  (`data_access_logic/meme/extractor.py` の `refresh`)と、出来事・話ならその場での要約(`event_summary` / 話の `summary_text`。
  本文が変わっていれば作り直す)をまとめて行うので、`ExtractMemes` を別に呼ぶ必要は無い。`CommitEvent` はさらに出来事の種を抜き出す
  (下の「出来事の生成・話の材料」)。確定の入口を通らなかった分の
  取りこぼしをまとめて拾いたいときは `RefreshGeneratedContent` を呼ぶ。これらの経路で足したミームは
  検めない(`# 検証結果` の節が無いまま)ので、`CheckFacts("meme")` で後から埋める
- 話は `episode` テーブルに一話一行で持つ。枠(`plot_text`。作者が入れるプロット、AI 生成前)と
  本文(AI か作者が書く、投稿する本文。`main_text`)を同じ行に持ち、時期・場所・視点は
  `start` / `end` / `location_id`(Location への FK)/ `viewpoint_character_id`(Character への FK)に入る。
  登場人物は `episode_character`(中間テーブル、多対多)で持つ。字数(`letters`)は本文から数える。
  `episode_character` の `mentioned` が true の行は、登場せずプロット・本文に名前が出るだけの人物(下の「名前だけ出る人物」)。
  本文の概要(`summary_text`)と、概要を作った本文の sha256(`summary_source_hash`)も同じ行に持つ。
  書いたモデル・effort は db に残さない(選択肢はその場の Claude 呼び出しにだけ効く)
- 本文に字数の指定は無い(`ai/instructions/style.py` の `EPISODE_STYLE_BASE`)。筋(プロット、場面を手番で演じたならその行)と、渡された作品・登場人物・場所・
  直前の話・関係する設定などの周辺データを踏まえ、具体的な描写・会話・人物の動きまで詳しく書き起こす。
  場面の数と一場面の長さは決めず、中身に合わせる。プロットの形は `ai/instructions/plot.py` の `PLOT_FORMAT_INSTRUCTION`
  (枠の生成・プロット補完・スキル `episode` が共に使う。300〜500 字を目安に `## 場面` の箇条書き(`場所 / 出る人 / そこで変わること`)と `## 狙い`):

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
種は作品の本文・話のプロット(`plot_text`、無ければ本文)・人物の `plot`・出来事の本文から、時代・場所・固有名詞を抜いて抜き出したもの
(`data_access_logic/event_seed/extractor.py` の `refresh`。`event_seeded` が false の元だけから抜き出して true にする。
似た種は `consolidate` でまとめる)。抜き出しは、出来事を足す入口(`CommitEvent` / `GenerateEvent`)が、足したあとに
確定とは別のセッションで行う(足した出来事自身の本文も元になる。AI が答えなくても出来事は残る)。
GUI の表から足したとき(`execute(s)`)は抜き出さず、次に入口から出来事を足したときにまとめて拾う。
その場所か当事者に掛かる「この時点より後に既に決まっている出来事」は、要約を添えて記録を決める段に渡し、矛盾させない。

話の本文は、生成関数ではなくこのセッションの Claude が書く・直す(スキル `episode` / `revise-episode`)。
材料は `ReadEpisodeCasting` / `ReadEpisodeBrief`(`data_access_logic/episode/brief.py`)で読み、`CommitEpisode` で確定する。
枠の生成(`GenerateFrame`)・プロット補完(`CompletePlot`)は、渡した値をまず話の行(枠)と登場人物(`episode_character`)として保存し
(`data_access_logic/episode/form.py`)、その行だけから材料を読む(`data_access_logic/episode/material.py`)。
話に渡す登場人物は、話と人物のリレーション(`episode_character`)だけ。`character_ids` を渡せばそれでリレーションを置き換え、
省けば枠の `episode_character` を使う。

**名前だけ出る人物**: 登場人物でなく、プロット・本文に名前が出る人物・対象は、`episode_character` に
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
ここでの同じ作品は、話の作品と、その親の作品・親を同じくする作品(章・外伝)を合わせたもの。章の頭の話にも前の章の話が見本として渡る(親の無い作品は同じ作品だけ)。
見本からは文体だけを汲ませ、中身は読み取らせない(`ai/instructions/past_episodes.py`)。章・外伝をまたぐ話には作品名を添える。作品の筋書きは、親の作品を「親の作品」としてたどって渡す。
枠を作るとき(`framer`)は本文を渡さず、前の話をすべて概要で渡す。
概要の無い話は書く前に作る(本文が変わっていなければ作り直さない)。
登場人物ごとに、その時点の歳・人となり・口調・相関・直近の出来事(要約)を渡す。話の場所(無ければ作品の立つ場所)の
直近の出来事と、その場所か登場人物に掛かる「この時点より後に既に決まっている出来事」も渡し、矛盾させない。
プロット補完では、プロットから中間段でアイデアを引いて「関係する設定」として渡す。
Claude のモデルの既定は `claude-opus-5-5` の `low`(`ai/claude_code/ai_client.py` の `MODEL` / `EFFORT`)。待ち時間の既定は `DEM_CLAUDE_AI_TIMEOUT`(600 秒)で、それより長く待つ呼び出し(事実確認)だけが `timeout` を渡す。

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
- `fact_check/` — oracle・ミームを AI に Dラボのナレッジとネット検索で検めさせ、妥当性と補足を書く(`ai/claude_code/fact_checker.py`)
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

入口の基底は `entrypoint.py` に置く。AI を回す入口の `result()` は、流れ(`flows/`)を呼ぶだけにする(下の「AI を呼ぶ処理と、流れ・段」)。
読む入口が返す行の組み立ては、各領域の `reading.py` に置く(`event/reading.py` の `EventRow`、`character/reading.py` の `CharacterSheet` など)。

```
Entrypoint(entrypoint.py)
├─ SessionEntrypoint            db セッションを開いて execute(s) へ渡す
│   ├─ CommitEntrypoint         「確定する」系。execute(s) を s.begin() に包む。GUI の API も execute(s) を呼ぶ
│   │   ├─ commit_*.py / update_*.py / delete_*.py / merge_idea.py / set_episode_synced.py
│   │   ├─ idea.resolve_ideas.ResolveIdeas / idea.link_ideas.LinkIdeas(候補を足す・結ぶので確定側)
│   │   └─ CommitEvent / UpdateEvent / CommitEpisode / CommitStory / CommitOracle  execute(s) は段を呼んで確定だけ、
│   │                           result() は確定のあとの AI(ミーム・要約・種・事実確認)まで流れ(flows/commit.py)で回す
│   ├─ ListEntrypoint           select() の行を row() でモデルにして並べる → list_locations / list_characters / list_character_relations / list_events
│   └─ read_*.py / list_*.py / start_story.py / search_ideas.py / list_pending_reviews.py / draw_memes.py
├─ AI を回す入口(generate_*.py / complete_plot.py / read_episode_brief.py / read_episode_casting.py / rewrite_episode_summary.py /
│   extract_memes.py / refresh_generated_content.py / check_facts.py)  result() で流れ(flows/)を呼ぶだけ
└─ RandomDraft                  db に触れない下書き作成 → create_random_*.py
```

### AI を呼ぶ処理と、流れ・段

AI を呼ぶ処理は、db だけの関数(対象を引く `*_targets`、材料を組む `*_material`、書き戻す `save_*`)を `<領域>/steps.py` の段
(`@db_step`。`step.py`)にし、AI だけの関数(`*_draft`。材料のモデルを受けて AI の出力のモデルを返し、db に触らない)と分けて置く。
二つをつなぐ流れは `flows/` に一つだけ持ち、段は `caller.call` で呼ぶ。手元では段を自分のセッションで回し、
db に繋がない Claude Code on the web のセッションでは、`web_session/flows.run` が口を API(`POST /api/steps/<領域>.steps.<関数名>`)に
差し替えて同じ入口を回す(`.docs/claude-tasks.md`)。

- 段は一つのトランザクションで回り、終わりに commit する(AI の結果を書き戻す段を一回呼ぶのが一つの commit)。段の中で commit しない
- 段の入力・出力は pydantic のモデル。出力は `*Serialized` でない土台のマテリアルで宣言する(web では列のまま JSON で運ぶ)
- claude を叩く入口を足したら、段と `flows/` の流れも足す

## 引き方は query 側にある

読む側の中身は `data_access_logic/query/` にある。

| モジュール                     | 何のため                                                     |
| ------------------------------ | ------------------------------------------------------------ |
| `common_query.py`              | 時刻の扱い・断面・顔ぶれ・場所の道筋                         |
| `period.py`                    | その時刻に期間(`start` 〜 `end`)が掛かる行の条件(`alive_at`) |
| `character_simulation_query.py` | 人物を軸に周辺を読む(`read_surroundings`)                   |
| `dictionary_query.py`          | アイデア(辞書)の検索。名前・本文(`idea_history` を左外部結合した作中の呼び名も含む)の部分一致、場所・時刻の範囲 |
| `story_creation_query.py`      | 場所に掛かる作品(`story`)の読み出し                          |
| `world_creation_query.py`      | 生きている人物、広さの整合、進行中の判定               |
| `event_seed_query.py`          | 出来事の種をまだ抜き出していない元(`event_seeded` が false) |
| `review_query.py`              | ユーザの判断が要るもの(本文に残った TODO・世界観へ反映していない話) |

入口のファイルはその薄い呼び出し面で、**SQL は組み立てない。**
引く条件は時刻とレコードの id だけで表す。足りない引き方が出てきたら
query 側に関数を足して、ここに入口を一つ被せる。
