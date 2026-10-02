# db の読み取りと AI とのやり取り(pydantic)

見本は `data_access_logic/episode/` と `data_access_logic/idea/`。既存の処理を直すときもこの形へ寄せる。

- 既存の処理をなぞらず、要るものからゼロベースで組む
- 書く対象の行が持つ値(時刻・作品など)は引数にせず、行から取る
- 引数名は何の数・何の範囲かが分かる名前にする(`count` ではなく `past_episode_count`)
- 理由の言えない構文(キーワード専用の `*` など)は付けない
- select の結果は pydantic のモデル(マテリアル。基底は `data_access_logic/material.py` の `Material`)に、ORM のまま渡して詰める。
  `reportArgumentType` は `pyrightconfig.json` で切ってあるので、`Model(story=story_row)` と渡してよい
- マテリアルは ORM の列とリレーションに忠実に写す。リレーションは同じ名前のフィールドに、関係先のモデルを入れ子で持つ(`AliasPath` などで平らにしない)
- 共通の列は基底のモデルに置き、継承先にはそのとき読むリレーションだけを書く
- リレーションは要るものだけを `joinedload` / `selectinload` で読み、`execution_options(populate_existing=True)` を付ける(無いと、同じセッションに残った行で eager load が効かず黙って空になる)
- 問い合わせの回数が増えても、シンプルに持てる方を選ぶ
- `execute` はなるべく使わず、`scalars` / `scalar` で ORM を取る
- リレーションが足りなければ、`schema.py` に読み取り専用(`viewonly=True`)で足す
- マテリアルには見出し(エイリアス)を付けない
- AI に渡す形は、マテリアルを継承した `*Serialized` の `model_serializer` で組む。見出しは日本語にし、管理用の値(id・`confirmed` など)を外し、要るものだけを抜き出す。null・空の値も消さずに渡す
- AI の出力も pydantic のモデルで受ける。AI の client の `generate(prompt, 出力のモデル, ...)` に渡すと、json schema を作ってそのモデルで返す(得られなければ None)
- 出力の整形・検証はバリデータに置く
- 出力のモデルには docstring を書かない(schema の description として AI に渡る)
- dict の `.get` や文字列キーでの取り出しは極力使わない。既存の関数が dict を返すなら、境目でモデルに読み込んで属性で扱う
- dict への変換・二重の変換は残さない。関数は最初からモデルを返す(呼ぶ側で `model_validate` し直さない)
- フォームは ORM の行へ属性で書く(`Model(**form.model_dump())` や `model_copy(update=dict)` にしない)
- dict にするのは、API・CLI へ返す最後の `model_dump(mode="json")` だけ
- 既存のメソッド(`common_query` など)で済むものは自前で書かない
- 入口は `data_access_logic/<領域>/<動詞_対象>.py`。claude は `show()`、GUI の API は `execute(s)` を呼ぶ
- 入口の引数は `str | dict` にせず、pydantic のモデル(`data_access_logic/<領域>/form.py`)で受ける
- 入口のレスポンスもモデル(`data_access_logic/<領域>/record.py` など)で組み、`run()` が `model_dump(mode="json")` した結果を返す
- すべての引数に型を書く(AI は `ai: AIClient`)
- 時刻だけは `Stamp | str | None` で文字列も受ける(呼ぶ側が import を足さずに書ける)
- 呼ぶ側は時刻を `'11576/01/01'` のような文字列か `Stamp` で渡す。db の列の生の整数(`115760101000000`)は渡さない(年として読まれて止まる)
- 読み取りの入口では、時刻を `Stamp` に読み替えずそのまま渡す(文字列の精度が期間の幅になる。`"1200"` なら 1200 年の一年。`common_query.span`)
- 確定(commit)の境目:
  - AI を呼んで得た結果(要約・記録・本文・候補のアイデア・ミーム・種など)は、得たその場で commit する
  - 長い AI 呼び出しの前にも、それまでの保存分(話の枠など)を commit する
  - db だけの処理(`CommitEntrypoint` の `execute`)は入口のトランザクション(`s.begin()`)に任せ、中で commit しない
  - commit の後で ORM の行を使うときは、読み直すか先にマテリアルへ写しておく(commit で読み込んだ関連が期限切れになる)
