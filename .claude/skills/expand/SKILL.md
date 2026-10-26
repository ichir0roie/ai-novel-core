---
name: expand
description: 作者モード(世界の展開)。作者(ユーザ)が一言(「北の港で疫病が流行る」「ノアには姉がいた」「ep12 で二人を仲違いさせたい」)を言うたびに、それに関わるアイデア・ミーム・出来事(筋=プロットは出来事の親子で持つ)・人物・関係・来歴を AI の行として足し、関わる AI の行を直してつじつまを合わせる。作者の行(出自 user)には触れず、食い違いと作者の行を直す指示は案にして作者の判断を待つ。展開ごとに変えた行が記録され、取り消せる。作品全体を読み込んで整理するのもここ。話の本文(`main_text`)は書かない。「ex3」(3 は作品の id)、「ex3 北の港で疫病が流行る」、「ex 〇〇」、「世界を広げて」「この設定から枝葉を広げて」「作品全体を詰めたい」「全体の整合を見ながら筋を直したい」などの依頼で使う。人物が自分から動く人物モードはスキル `auto-act`。
---

入口・呼び方は `data_access_logic/readme.md` の「依頼内容 → 呼ぶコード」の表のとおり(手元は `.claude/docs/db.md`、web のセッションは `.claude/docs/web-db.md`)。設計は `.docs/world-expansion.md`。

- 合図: 「ex<作品id> <一言>」は、その作品の枝として一言を展開する。「ex <一言>」は作品を限らずに展開する。「ex<作品id>」だけなら、作品を読み込んで整理し(下の 1)、そのあとのメッセージを一言として受ける
- 作者の一言が本筋の正。AI が足した行はその肉付けで、作者の一言と作者の行に合わせて直してよい
- **作者の行(出自 `user`)には AI の書き手で触れない**。守り(`db/guard.py`)が止める。作者の行を直すのは、案を作者が認めてから、作者の書き手で(下の 3)
- 話の本文(`main_text`)は書かない・直さない。AI は話・作品を作らない(守りが止める)。筋(プロット)は出来事で持つ: 大きな筋を親の出来事(`start` / `end` で期間)、場面を子の出来事(`parent_event_id`)にする。本文に進むのは、作者が「ep<話id>」を頼んだときだけ
- 作者に尋ねずに AI の行を入れる(認めを待たない)。合わなければ作者が展開ごと取り消す(下の 4)

## 書き手と展開の id

展開(`expansion`)を一つ立て、その id と書き手を付けて書くと、守りが出自を入れて変えた行を記録する(`db/writer.py`)。

| 書き手 | いつ | 付け方 |
| --- | --- | --- |
| `ai` | 一言を広げる・AI の行を直す(下の 2) | 手元: python の中で `with writing('ai', <展開id>):` の中で入口を呼ぶ。web: db だけの入口は curl に `-H 'x-novel-writer: ai' -H 'x-novel-expansion: <展開id>'` を足す。claude を叩く入口(`flows.run`)は `with writing('ai', <展開id>):` の中で呼ぶ |
| `user` | 作者が認めた案で作者の行を直す(下の 3) | 上の `'ai'` を `'user'` にする(展開の id は付けたまま。取り消せるように) |

手元の呼び方(`.claude/docs/db.md` の「入口を呼ぶ」に `writing` を足したもの):

```
.venv/bin/python -c "
import json
from pathlib import Path
from data_access_logic.logs import configure_logging
from db.writer import writing
from gui.api import interface
configure_logging()
with writing('ai', <展開id>):
    print(json.dumps(interface.call(interface.entrance_class('<入口の id>'), {<引数>}), ensure_ascii=False, indent=2))
"
```

- 展開を立てる `StartExpansion`・終える `FinishExpansion`・食い違いを残す `AddConflict` は、書き手を付けずに呼んでよい(展開の記録の表は守りの外)
- `ProtectedRowError`(API なら 403)が返ったら、作者の行か AI に書かせない表に触れようとした。打ち直さず、作者の行なら食い違いの案にする(下の 2 の 5)

## 入口

| 行 | 入口 | 決まり |
| --- | --- | --- |
| 展開を立てる・終える | `expansion.start_expansion.StartExpansion` `{'expansion': {'mode': 'author', 'prompt': <作者の一言そのまま>, 'story_id': …, 'time': …, 'location_id': …}}` / `expansion.finish_expansion.FinishExpansion` `{'expansion': {'id': …, 'summary': …}}` | 一言ごとに一つ。`prompt` は言い換えずに入れる(後の展開が正として読む) |
| これまでの一言を読む | `expansion.list_expansions.ListExpansions` `{'mode': 'author', 'status': 'done', 'limit': 200}` の `prompt` | 作者の一言はどれも本筋の正 |
| 関わる行を引く | `world.search_world.SearchWorld` `{'words': [<語と言い換え>], 'story_id': …}` | 当たった行の `origin` で、AI が直せる行か作者の行かが分かる |
| 設定(アイデア) | `idea.resolve_ideas.ResolveIdeas`(当たらない語は候補として足す)・`CommitIdea` / `UpdateIdea`(AI の行だけ)・呼び名を足すのは `idea.append_history.AppendIdeaHistory` | 人名・場所の名前は足さない |
| 出来事(筋) | `event.commit_event.CommitEvent`(中身を決めて足す)・`event.generate_event.GenerateEvent`(場面の指定から AI に起こさせる)・`UpdateEvent` / `DeleteEvent`(AI の行だけ) | AI を回すので web では `run_in_background`。筋の親の出来事を先に足し、場面はその `parent_event_id` で子にする |
| 人物 | `character.generate_character.GenerateCharacter`(`plot_text` に主張を渡す)・`CommitCharacter`・来歴を足すのは `character.append_history.AppendCharacterHistory`・`UpdateCharacter`(AI の人物だけ。配列はまるごと置き換わる) | 作者の人物には来歴の行を足すだけ(`AppendCharacterHistory`) |
| 関係 | `CommitCharacterRelation`・来歴は `character.append_relation_history.AppendRelationHistory` | 間柄が変わるなら `end` で区切った新しい関係の行 |
| 場所 | `CommitLocation`・来歴は `location.append_history.AppendLocationHistory` | |
| 知る相手 | `character.add_knower.AddKnower` `{'table': '<来歴・呼び名の表>', 'row_id': …, 'knower': {'knower_id': …}}` | 秘密は人物だけを知る相手に |
| ミーム | `meme.extract_memes.ExtractMemes` `{'rows': [{'table': 'expansion', 'id': <展開id>}, {'table': 'event', 'id': …}]}` | 一言と足した出来事から抜き出す |
| 食い違いを残す | `expansion.add_conflict.AddConflict` `{'conflict': {'expansion_id': …, 'table_name': …, 'row_id': …, 'detail': …, 'proposal': …}}` | 作者の行にだけ残す(AI の行は直す) |
| 食い違いを決める | `expansion.resolve_conflict.ResolveConflict` `{'conflict': {'id': …, 'status': 'accepted' / 'dismissed'}}` | 下の 3 |
| 展開を読む・取り消す | `expansion.read_expansion.ReadExpansion` `{'expansion_id': …}` / `expansion.revert_expansion.RevertExpansion` `{'expansion_id': …}` | 下の 4 |
| 作品の筋書き・話の枠とプロット | `story.update_story.UpdateStory`・下の「話の行を書く」 | 作者の行。作者が認めた案だけ、作者の書き手で直す |
| 書き方 | `style_preference.read_writing_style.ReadWritingStyle` `{'writing_style': {'scope': '<書く文の範囲>'}}` | 行を書く前に読む。範囲は、出来事は出来事、人物の芯・筋書きは人物、来歴は来歴、関係は関係、設定の説明はアイデア、作品の筋書き・場所の説明は全体(`scope` を省く)、プロットはプロット |

### 話の行を書く

作者が認めた案で話の枠・プロットを直すときは、`CommitEpisode` の AI の段を回さず、確定の db の段だけで書く(作者の書き手で。話は AI の書き手では書けない)。プロットのような長い文字列はスクラッチパッドのファイルに置いて読む。

- 欄: 新しい枠は `story_id`・`start`(`<年/月/日>`)・`plot_text`・あれば `title`。既存の話は変える欄だけ。**`main_text` は渡さない**
- web のセッション: 足すのは `curl -sS -X POST -H "$h" -H 'content-type: application/json' --data-binary @<scratchpad>/<名>.json "$api/api/tables/episode/records"`、直すのは `-X PATCH` で `.../records/<話id>`(本文の JSON は `jq -n --rawfile p <プロットのファイル> '{plot_text: $p}'` のように組む)。展開の id は `-H 'x-novel-expansion: <展開id>'` で付ける
- 手元:

```
.venv/bin/python -c "
from pathlib import Path
from db.schema import get_env_session
from db.writer import writing
from gui.api import records, tables
with writing('user', <展開id>), get_env_session() as s, s.begin():
    records.update_record(s, tables.spec_of('episode'), <話id>,
                          {'plot_text': Path('<scratchpad>/<名>.txt').read_text(encoding='utf-8')})
"
```

  足すのは `records.create_record(s, tables.spec_of('episode'), {…})`

### 行ごとの決まり

どの行も、書く前にその文の範囲の書き方を `ReadWritingStyle` で読み、その書き方で書く(このスキルの中に書き方を足さない)。

- プロット: プロットの範囲の書き方で書き直して、「話の行を書く」で入れる。作者が「保留」「迷っている」としたものは、関わる場面の文の中に「〜か〜かは迷っている」と書いて置く(スキル `episode` は、この文が残っていれば書く前に尋ねる)。端役には名前を付けず、役割か見た目で書く
- プロットの台詞: 作者が言わせたい台詞は「」で括り、誰の言葉かが分かるように書く。その人物がそう言う・動く理由になる記憶・出来事が来歴・関係に無ければ、足す行も案に挙げる
- 人物: 来歴は起きた時刻を `start` にした行を出来事ごとに足す(時期の違う出来事を一つの行にまとめない。時期の決まらない構想は `start` を空にした行)。行にはその時刻のことだけ、先のことは先の時刻の行へ(`data_access_logic/readme.md` の「人物の来歴」)。秘密は知る相手を本人だけにし、知る相手が決まっていればその人物を入れる。芯(`text`)は時期を限らない人物像だけ、行く末・作中の役回りは筋書き(`plot`)に書く。二人のあいだで起きたことは関係の来歴に書き、人物の来歴には本人に起きたこと・変わったことだけを書く(秘密は人物の来歴へ)
- 関係: `text` は時期を限らない芯だけ、起きたこと・変わったことは起きた時刻の来歴の行を足す(`data_access_logic/readme.md` の「関係の芯と来歴」)。間柄そのものが変わるなら、`end` で区切った新しい関係の行にする。関係の来歴に書いたことは、人物の来歴に繰り返さない
- 設定: 無ければ `ResolveIdeas` / `CommitIdea`(話に出る語なら `AddIdeas`)で足す。作中の呼び名は来歴(`histories`)の行に書く
- 場所: `text` は時期を限らない場所の姿だけ、起きたこと・変わったことは起きた時刻の来歴の行を足す(`data_access_logic/readme.md` の「場所の芯と来歴」)
- 話の登場人物・場所: `CastEpisode`(登場人物はまるごと置き換わる。作者の行なので、作者が認めた案だけ)

## 1. 作品を読み込む(「ex<作品id>」だけのとき)

この段では行を直さない。

1. **作品を読む**: 作品の名前・筋書き(`text`)すべてと、子の章・外伝(`ListStories` の `parent_story_id`)を読む
2. **話の並びを読む**: `ReadEpisodes` `{'story_id': …, 'count': 500, 'text': False}`(子の作品のぶんも)。登場人物・名前だけ出る人物は、web は表の API の `episode` の行の `character_ids`・`mentioned_character_ids`、手元は `episode_character`。プロットは `ReadEpisodeTexts` `{'episode_ids': […]}` の `plot_text` で読む(本文も返るので、出力はスクラッチパッドへ書き出す)
3. **人物・関係・場所・筋を読む**: 話の人物と `ReadCast` `{'story_id': …}` の顔ぶれを時刻を渡さない `ReadCharacter` で、関係を `ListCharacterRelations` で、話の場所とその親を表の API の `location` で、人物・場所の出来事を `ReadEvents` で読む。これまでの作者の一言(`ListExpansions`)も読む
4. **整理する**: `<scratchpad>/expand/<作品id>-map.md` に、年表(話と筋の出来事を時刻の順に一行ずつ)・人物・関係・場所・作者の一言・気になる所(下の 2 の 5 の観点で見つけた食い違い)をまとめる。展開のたびに読み直し、変えた分を書き換える
5. **返す**: 筋書きの要点(三行ほど)・年表・主な人物と関係・気になる所を返し、一言を待つ

## 2. 一言を受けたら(広げる)

作者のメッセージ一つを一言として受け、次の順で回す。作者に尋ねるのは、一言の時刻・場所がどうしても決まらず、決め方で大筋が変わるときだけ(一つだけ尋ねる)。

1. **展開を立てる**: `StartExpansion`(`prompt` に一言をそのまま、作品・時刻・場所が分かれば添える)。ここから先は、返った id と書き手 `ai` を付けて書く
2. **読み解く**: 一言を主張に分ける(設定・出来事・人物・関係・筋)。主張ごとに時刻・場所・関わる人物を決める。決まらなければ、作品の書き進めた所(本文のある話の一番新しい時刻)とその場所を取る。作者の行を名指しで直す指示(「ep12 のプロットを〜に」「ノアの来歴を〜に」)は、広げずに案にする(下の 5)
3. **引く**: 主張の語と言い換えで `SearchWorld` を引き、当たった行と一段広げた行(`linked`)を読む。設定は `ResolveIdeas` で照らす。これまでの作者の一言を `ListExpansions` で読む
4. **広げる**: 主張ごとに、要るものだけを足す。一回の展開で足す行は 30 行ほどまで(広がり続けないように)。書く前に、その文の範囲の書き方を `ReadWritingStyle` で読む
   - 設定 → アイデアと、効く場所・時期の呼び名の行。作中の人が知るなら知る相手を付ける
   - 出来事 → 出来事と、当事者・場所の来歴の行。結果の出来事が続くなら、それも時刻つきで足す
   - 筋 → 出来事の木。筋の全体を親の出来事にし、場面を子の出来事にする。本筋の書き進めた所より先の時刻の出来事は、後の生成に「後に決まっている出来事」として渡って筋を守らせる。サブキャラクターの来歴の行は、出来事の時刻が来るまで(本文のある話の時刻を越えて)足さない
   - 人物 → `GenerateCharacter` と関係。作者の人物に起きたことは `AppendCharacterHistory` で来歴の行を足す(秘密は知る相手を絞る)
   - ミーム → 一言と足した出来事から `ExtractMemes`
5. **つじつまを合わせる**: 足した行と 3 で引いた行を、作者の一言(これまでの分もすべて)・作者の行と照らす。観点は、時刻(出来事・話の順、年齢・生没年、関係の始まり、居場所)・人物(芯・来歴・筋書きと行い)・関係(間柄とやり取り)・知ること(秘密の知る相手と振る舞い)・設定(説明・呼び名と使い方)・場所(説明・来歴と描き方)・伏線(張った所と回収する所)
   - 食い違う相手が AI の行(`origin` が `ai`) → 作者の一言と作者の行に合うように直すか消す(書き手 `ai`)
   - 食い違う相手が作者の行 → 直さずに `AddConflict` で残す。`proposal` に、直す行と直したあとの中身を具体に書く。本文のある話は、本文を直す案ではなく、どこが合わなくなるかを書く
   - 作者の行を名指しで直す指示(上の 2)も、`AddConflict` で案にする
   - 直したことで新しい食い違いが出ていないかを、もう一巡だけ確かめる(二巡で止める)
6. **終える**: `FinishExpansion`(`summary` に、足した・直した・消した行の要点)。`<作品id>-map.md` を書き換える
7. **返す**:

   ```
   ## 展開 <展開id>
   <一言を一二行で言い直したもの>

   ## 足した・直した(AI の行)
   - 出来事 <名>(id=…): <要点>
   - 人物 <名>(id=…): <要点>
   …

   ## 決めてほしいこと(作者の行)
   1. 食い違い id=<id> / <表> <名>(id=…): <何と何が食い違うか> → 案: <直したあと>
   …
   ```

   - 何も無い節は省く。食い違いを解く道が二つ以上あれば、案の中で `1a` / `1b` と並べる

## 3. 作者が決めたら

作者が案に答えたら(「1 は受ける」「2 は捨てる」「1 は〜にして」)、答えた食い違いだけを片付ける。

- 受ける: 案のとおりに、作者の書き手(`writing('user', <展開id>)`)で作者の行を直す。話の枠・プロットは上の「話の行を書く」、人物・関係・場所・設定は入口の表の入口(作者の人物の来歴の配列を直すなら、時刻を渡さない `ReadCharacter` で今の行をすべて読んで渡す)。直したら `ResolveConflict` を `accepted` に
- 捨てる: `ResolveConflict` を `dismissed` に。AI の行のほうを作者の行に合わせる必要があれば、書き手 `ai` で直す
- 直す中身が案から大きく変わるなら、案を出し直す
- 決めていない食い違いは `review.list_pending_reviews.ListPendingReviews` に残り続ける

## 4. 取り消す

「展開 <id> を取り消して」で `RevertExpansion`。展開で足した行を消し、直した・消した行を戻す。展開のあとで作者か別の展開がその行を直していたら、何も戻さずに止まるので、どの行かを作者に伝える。

## 5. 終える

作者が終わりを告げたら(「ここまで」「終わり」など)、このモードで回した展開の一覧(id・一言・足した/直した/消した数)と、決めていない食い違いの一覧を返す。本文に進むなら「ep<話id>」を、と一行添える。自分から本文に進まない。
