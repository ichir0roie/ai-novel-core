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

文体・作風・書き方の注意書きは、作風に依存するので、`core`(このリポジトリ)に定数として持たず、db の `style_preference` 表に持つ。

- 書き方の文(文体・筋と場面・セリフ・注意書きなど)を、`ai/instructions/` の定数に足さない。行として db に足す(GUI の「文体の好み」の一覧か、入口 `style_preference.commit_style_preference.CommitStylePreference` / `update_style_preference.UpdateStylePreference`)
- 行ごとの効く範囲(`scope`)は広さの段で並ぶ。全体 → ストーリー(`story_id` の作品と子孫の作品) → 使う所の範囲(本文・プロット・人物・出来事・アイデア・ミーム・関係)。使う所は、上の段をすべて足す。足し方と順は `data_access_logic/readme.md` の「出来事の生成・話の材料」の表
- 何の範囲に置くか迷ったら、広い方に置かない。全部の文に効かせたい決まり(語の選び方・抽象的な言い方を避けるなど)だけを全体に、作品の作風はストーリーに、本文だけ・プロットだけの決まりはその範囲に置く
- 初期値の行(誰がクローンしても始めから効く最低限の書き方)は `db/style_defaults.py`。`init_db`(`seed_master_rows`)とマイグレーションで入れる。初期値を足す・直すときは、行を足すマイグレーションも書く(同じ文面の行があれば足さない)
- コードに残すのは、本文の整形(`layout_novel_text`)と結びついた約束(「◇」・行の組み方。`ai/instructions/style.py` の `EPISODE_LAYOUT_INSTRUCTION`)と、仕組み・安全に関わる文(`ai/instructions/` のほかの定数)だけ
- 生成の system に、文の書き方(語の選び方・慣用句など)を個別に書き足さない。どの生成にも `generate` が同じ書き方を足す。AI を呼ぶ所は `generate(style_scope=…, story_id=…)` で、書く文の範囲と作品を渡す(作品が分かる所だけ)
- db から読むのは `data_access_logic/style_preference/extras.py`。行が無ければ空のまま動く
- このセッションの Claude が自分で本文を書く・直すとき(スキル `episode` / `revise-episode`)は、`ReadEpisodeBrief` の材料の「書き方」に、本文の範囲の書き方(全体 → ストーリー → 本文)が入る(`data_access_logic/episode/brief.py`)。本文でない文(プロット・来歴・関係・アイデア・場所の説明など)を書くときは `ReadWritingStyle` で、書く文の範囲と作品を渡して読む
