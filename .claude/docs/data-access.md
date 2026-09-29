# db の読み取りと AI とのやり取り(pydantic)

`data_access_logic/episode/` と `data_access_logic/idea/` がこの形の見本。既存の処理を直すときも、この形へ寄せる。

- 既存の処理をなぞらず、その処理に要るものからゼロベースで組む。書く対象の行が持つ値(時刻・作品など)は引数にせず行から取り、
  引数名は何の数・何の範囲かが分かる具体的な名前にする(`count` ではなく `past_episode_count`)。理由の言えない構文(キーワード専用の `*` など)は付けない
- select の結果は pydantic のモデル(マテリアル。基底は `data_access_logic/material.py` の `Material`)に、ORM のままを渡して詰める。
  型チェッカーの `reportArgumentType` はプロジェクト設定(`pyrightconfig.json`)で切ってあるので、`Model(story=story_row)` のように渡してよい
- マテリアルは ORM の列とリレーションに忠実に写す。リレーションは同じ名前のフィールドに、関係先のモデルを入れ子にして持つ
  (`AliasPath` などで平らにしない)。共通の列は基底のモデルに置き、継承先にはそのとき読むリレーションだけを書く
- リレーションは要るものだけを `joinedload` / `selectinload` で読み、`execution_options(populate_existing=True)` を付ける
  (同じセッションに行が残っていると eager load が効かず、黙って空になる)。問い合わせの回数が増えても、シンプルに持てる方を選ぶ。
  `execute` はなるべく使わず `scalars` / `scalar` で ORM を取る。リレーションが足りなければ `schema.py` に読み取り専用(`viewonly=True`)で足す
- マテリアルには見出し(エイリアス)を付けない。AI に渡す形はマテリアルを継承した `*Serialized` の `model_serializer` で組む。
  AI が誤解しないよう見出しを日本語にし、管理用の値(id・`confirmed` など)を外し、要るものだけを抜き出す。値が null・空でも消さずに渡す
- AI の出力も pydantic のモデルで受ける。AI の client の `generate(prompt, 出力のモデル, ...)` に出力のモデルを渡すと、
  client が json schema を作ってそのモデルで返す(得られなければ None)。整形・検証はバリデータに置く。
  このモデルの docstring は schema の description として AI に渡るので書かない
- dict の `.get` や文字列キーでの取り出しは極力使わない。既存の関数が dict を返すなら、境目でモデルに読み込んでから属性で扱う
- dict への変換と二重の変換は残さない。関数は最初からモデルを返し(呼ぶ側で `model_validate` し直さない)、フォームは ORM の行へ属性で書く
  (`Model(**form.model_dump())` や `model_copy(update=dict)` にしない)。dict にするのは API・CLI へ返す最後の `model_dump(mode="json")` だけ
- 既存のメソッド(`common_query` など)で済むものは自前で書かない
- 入口(`data_access_logic/<領域>/<動詞_対象>.py`。claude は `show()`、GUI の API は `execute(session)` を呼ぶ)の引数は、`str | dict` にせず pydantic のモデル(`data_access_logic/<領域>/form.py`)で受ける。
  レスポンスもモデル(`data_access_logic/<領域>/record.py` など)で組み、`run()` が `model_dump(mode="json")` した結果を返す
- 確定(commit)の境目: AI を呼んで得た結果(要約・記録・本文・候補のアイデア・ミーム・種など)は、得たその場で commit する。
  長い AI 呼び出しの前にも、それまでの保存分(話の枠など)を commit する。途中で AI が落ちても、それまでに得た結果は残す。
  db だけの処理(`CommitEntrypoint` の `execute`)は入口のトランザクション(`session.begin()`)に任せ、中で commit しない。
  commit すると読み込んだ関連が期限切れになるので、commit の後で ORM の行を使うときは読み直すか、先にマテリアルへ写しておく
