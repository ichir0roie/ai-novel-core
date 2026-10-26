# db と AI のコード

## 読み取りと AI とのやり取り(pydantic)

見本は `data_access_logic/episode/` と `data_access_logic/idea/`。既存の処理を直すときもこの形へ寄せる。

- 既存の処理をなぞらず、要るものからゼロベースで組む
- 書く対象の行が持つ値(時刻・作品など)は引数にせず、行から取る
- 引数名は何の数・何の範囲かが分かる名前にする(`count` ではなく `past_episode_count`)
- 理由の言えない構文(キーワード専用の `*` など)は付けない
- select の結果は pydantic のモデル(マテリアル。基底は `data_access_logic/material.py` の `Material`)に、ORM のまま渡して詰める。`reportArgumentType` は `pyrightconfig.json` で切ってあるので、`Model(story=story_row)` と渡してよい
- マテリアルは ORM の列とリレーションに忠実に写す。リレーションは同じ名前のフィールドに、関係先のモデルを入れ子で持つ(`AliasPath` などで平らにしない)。共通の列は基底のモデルに置き、継承先にはそのとき読むリレーションだけを書く
- リレーションは要るものだけを `joinedload` / `selectinload` で読み、`execution_options(populate_existing=True)` を付ける(無いと、同じセッションに残った行で eager load が効かず黙って空になる)
- 問い合わせの回数が増えても、シンプルに持てる方を選ぶ
- `execute` はなるべく使わず、`scalars` / `scalar` で ORM を取る
- リレーションが足りなければ、`schema.py` に読み取り専用(`viewonly=True`)で足す
- マテリアルには見出し(エイリアス)を付けない。AI に渡す形は、マテリアルを継承した `*Serialized` の `model_serializer` で組む。見出しは日本語にし、管理用の値(id など)を外し、要るものだけを抜き出す。null・空の値も消さずに渡す
- AI の出力も pydantic のモデルで受ける。AI の client の `generate(prompt, 出力のモデル, ...)` に渡すと、json schema を作ってそのモデルで返す(得られなければ None)。整形・検証はバリデータに置き、docstring は書かない(schema の description として AI に渡る)
- dict の `.get` や文字列キーでの取り出しは極力使わない。既存の関数が dict を返すなら、境目でモデルに読み込んで属性で扱う
- dict への変換・二重の変換は残さない。関数は最初からモデルを返す(呼ぶ側で `model_validate` し直さない)。フォームは ORM の行へ属性で書く(`Model(**form.model_dump())` や `model_copy(update=dict)` にしない)
- dict にするのは、API・CLI へ返す最後の `model_dump(mode="json")` だけ
- 既存のメソッド(`common_query` など)で済むものは自前で書かない
- 入口は `data_access_logic/<領域>/<動詞_対象>.py`。claude は `show()`、GUI の API は `execute(s)` を呼ぶ。引数は `str | dict` にせず、pydantic のモデル(`data_access_logic/<領域>/form.py`)で受ける
- 入口のレスポンスもモデル(`data_access_logic/<領域>/record.py` など)で組み、`run()` が `model_dump(mode="json")` した結果を返す
- すべての引数に型を書く(AI は `ai: AIClient`)。時刻だけは `Stamp | str | None` で文字列も受ける(呼ぶ側が import を足さずに書ける)
- 呼ぶ側は時刻を `'11576/01/01'` のような文字列か `Stamp` で渡す。db の列の生の整数(`115760101000000`)は渡さない(年として読まれて止まる)
- 読み取りの入口では、時刻を `Stamp` に読み替えずそのまま渡す(文字列の精度が期間の幅になる。`"1200"` なら 1200 年の一年。`common_query.span`)
- 確定(commit)の境目:
  - AI を呼んで得た結果(要約・記録・本文・候補のアイデア・ミーム・種など)は、得たその場で commit する
  - 長い AI 呼び出しの前にも、それまでの保存分(話の枠など)を commit する
  - db だけの処理(`CommitEntrypoint` の `execute`)は入口のトランザクション(`s.begin()`)に任せ、中で commit しない
  - commit の後で ORM の行を使うときは、読み直すか先にマテリアルへ写しておく(commit で読み込んだ関連が期限切れになる)

## schema

- 列の定義は `db/schema.py` が唯一の正。列名・型は db に問い合わせず推測もせず、`db/schema.py` を Read して確かめる(`episode` の題は `title`。推測で書くと `UndefinedColumn` で落ちる)
- NULL を持てる列で並べるときは NULL の向きを明示する(降順は `.nulls_last()`)。`DISTINCT` の結果を順番どおりに使うなら `order_by` を付ける
- PostGIS の列は `db/postgres/postgis.py`(`.docs/postgres.md`)
- すべての表は基底の `Base` から `created_at`(作った時刻)・`updated_at`(直した時刻)を持つ。どちらも db が入れる(既定値の `now()` と、PostgreSQL の関数 `set_updated_at` を呼ぶ表ごとのトリガー。`db/postgres/timestamps.py`)ので、コードから書かない。表を足すときのトリガーは `init_db` と alembic の autogenerate が自動で掛ける

### マイグレーション

- 置き場は `db/alembic/`。コマンド例は `db/alembic/README`
- `schema.py` を変えたら alembic で `revision --autogenerate` → 内容確認 → `upgrade head`(手元の開発用の db に当てる)。AWS の db へ当てる決まりは `.claude/docs/aws.md` の決まり 1
- 列を消す変更は、マージから API の差し替えまでの 1〜2 分だけ古い API が失敗しうる
- 新しいマイグレーションの確かめに、空の db から `upgrade head` で一から上げない(古いバージョンに PostgreSQL で通らないものがあり落ちる)。代わりに、変える前のコミットを `git worktree add --detach <スクラッチパッドの dir> <コミット>` で取り出し、その `db.postgres.init_db --url <テスト用のサーバーの別の db> --create-database` で表を作ってバージョンを付け、行を足してから、今のブランチで `alembic upgrade head` と `alembic check` を回す
- マイグレーションのテスト(上げ下げの往復)は書かない

## 世界ごとの好み(AI へ渡す文面)

AI へ渡す文面は db の行(書き方・作風)を土台にし、コードには、それが無いと仕事が成り立たない文だけを持つ。コードの文は作風によってはノイズになるので、短く、役割ごとに分ける。

- コードに持つ: 仕事ごとの指示(何を渡し、何をさせるか)・材料の読み方(見出しの意味、null の扱い、時点の読み方)・出力の欄の決まり(id は候補からだけ選ぶ、無ければ空、件数・字数、仮置き `【名前】` など)・どの生成にも効く禁止事項
  - 書き方・作風・良し悪しの好み(語の選び方、名前の付け方の趣味、何を厚く書くか、例文)はコードに書かない。db の書き方の行への誘導(「書き方の〜の基準で」)も書かない(db の行はどの生成にも足される)
  - 理由・言い換え・例は、無いと決まりが読み取れないときだけ書く
  - 仕事ごとの指示は、AI を呼ぶモジュールの定数(`_SYSTEM` など)にし、`generate(system=…, style_scope=…)` で渡す
  - いくつもの仕事で使う材料の読み方と、どの生成にも効く禁止事項は `ai/instructions/materials.py`。見出し一つにつき定数一つ。`generate` が足すのは禁止事項(`SAFETY_NOTE`)だけで、材料の読み方(`TIME_NOTE`・`LATER_EVENTS_NOTE` など)は、その見出しの材料を渡す仕事の指示にだけ入れる
  - 分類の一覧・件数のようなコードの値は、AI に渡す材料(プロンプト)に入れる
- db に持つ: 文体・作風・書き方の注意書き・行の組み方。作風に依存するので、`core`(このリポジトリ)に定数として持たない
  - 全体と使う所の範囲(本文・プロット・人物・来歴・出来事・アイデア・ミーム・関係・人物役・語り部・推敲。`db/schema.py` の `StyleScope`)ごとに `style_preference` に一行。推敲の行は、これまでの推敲で直したことと直し方の記録で、スキル `revise-episode` が推敲のたびに整理して書き直す。作品ごとの本文の決まりは `story.instruction`、話ごとの本文の決まりは `episode.instruction`(本文の範囲だけに足す。空なら足さない)
  - db の行に、材料の形・出力の欄・仕事の手順のような挙動の文を書かない
  - スキル・エージェントの定義にも書き方を書かない。文を書く所ごとに、その範囲の行を読んで従う(スキルは `ReadWritingStyle`・`ReadEpisodeBrief` の「書き方」、手番の語り部は `ReadWritingStyle` の語り部の範囲、人物役・対話役は `tool.episode_session style`)。語り部の範囲には、語り・要求の言い回しと、場面の運び方の好み(手番の絞り方・プロットの台詞の促し方・状況の起こし方)を置き、手番の JSON の形・コマンド・番の送り方は挙動としてスキルに残す。材料・仕組みに関わる決まり(材料の言い回しを写さない、端役に名前を付けないなど)は挙動として残す
  - 足すのは GUI の `style_preference` の画面、作品・話の画面の `instruction`、入口 `style_preference.commit_style_preference.CommitStylePreference`(範囲の行の末尾に足す) / `update_style_preference.UpdateStylePreference`
- 足す順は 全体の行 → その範囲の行。本文の範囲だけ 全体の行 → 作品の指示(祖先から) → 本文の行 → 推敲の行 → 話の指示(`data_access_logic/readme.md` の「出来事の生成・話の材料」)
- 何の範囲に置くか迷ったら、広い方に置かない。全部の文に効かせたい決まりだけを全体に、作品ごとの本文の決まりは作品の指示に、本文だけ・プロットだけの決まりはその範囲に置く
- 文体の文は db にだけ持つ。コードに初期値を置かず、`init_db` やマイグレーションで行を足さない(`init_db` で作った db には行が無く、行が無ければ空のまま動く)。文面を直すときは、db の行を入口で直す
- 生成の system に、文の書き方(語の選び方・慣用句など)を個別に書き足さない。どの生成にも `generate` が同じ書き方を足す。AI を呼ぶ所は `generate(system=…, style_scope=…)` で、仕事の指示と書く文の範囲を渡す(本文は AI の生成で書かないので、作品・話の指示は渡さない)。文を書かない仕事(id・番号・分類・検索語だけを返す)は `style_scope=None` にして書き方を足さない
- db から読むのは `data_access_logic/style_preference/extras.py`。行が無ければ空のまま動く
- このセッションの Claude が自分で本文を書く・直すとき(スキル `episode` / `revise-episode`)は、`ReadEpisodeBrief` の材料の「書き方」に、本文の範囲の書き方(全体 → 作品の指示 → 本文 → 推敲 → 話の指示)が、「材料の読み方」にコードの `EPISODE_BRIEF_NOTES` が入る(`data_access_logic/episode/brief.py`)。本文でない文(プロット・来歴・関係・アイデア・場所の説明など)を書くときは `ReadWritingStyle` で、書く文の範囲を渡して読む
