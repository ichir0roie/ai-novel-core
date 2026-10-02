# gui — データ編集 GUI

db(RDS)をブラウザから見て直すための道具。API(`gui/api`、FastAPI)と画面(`gui/web`、Next.js)の二つ。

- 未確認のアイデア・ミームを一件ずつ出し、直しながら「承認」「非承認」を付けて次へ進むレビュー画面
- 本文を持つテーブル(作品・話・人物・人物相関・出来事・場所・アイデア・ミーム・覚え書き・文体の好み)の一覧・表示・修正・追加
- 作品の一覧(`/tables/story`)は既定で、作品の親子(`parent_story_id`)の木。行の Move ボタンで移動モードに入り、親にする作品をクリックして付け替える。
  作品・話の一覧 API を引いてブラウザ側で組む(`gui/web/lib/storyTree.ts`)。`?view=list` で表に切り替える。
  枝の開閉はブラウザの localStorage に覚える(`gui/web/lib/treeOpen.ts`。既定は開いた状態)
- 星ごとの地図(`/maps`)と人物相関図(`/relations`)。元データは `/api/maps` `/api/relations`。ナビには出さず、
  場所の詳細から `/maps?location=<id>`(その場所を中心に置いて描く)へ、人物の詳細から `/relations?character=<id>`
  (その人物に関わる関係だけを描く)へ飛ぶ
- タイムライン(`/timeline?at=<時刻>&span=<日数>&story_id=&location_id=`)。中心の時刻の前後 `span` 日に掛かる話(作品ごとの段)と
  出来事を日の単位の軸に並べる(同じ日の札はその日の位置に時刻の順で縦に積み、期間はその日の始めから終わりの日の終わりまでの帯にする)。
  元データは `/api/timeline`。話・出来事の無い区間は斜線の帯に詰め(目盛りの欄に詰めた長さを出す)、
  残りの幅を中身のある区間に配る。札を横へドラッグすると、その日数だけ日付をずらして保存する(時・分・秒はそのまま。
  話は開始・終了、出来事は時刻・開始・終了を同じだけ動かす。話は手で直したのと同じく同期フラグが外れる)。札のクリックで編集、空の所のクリックで
  「Add episode」「Add event」を出し、どちらもモーダル(`RecordModal`)で開く(押した時刻・段の作品を初期値にする)。`at` を省けば最後の話の時刻を中心にする
- `data_access_logic/` の入口を画面(`/interface`)と API(`/api/interface`)から呼ぶ。
  `claude` コマンドを叩くものは Claude Code の環境(`CLAUDECODE=1`)で起こした API でだけ、裏の job として走る
  (Lambda など claude の無い所では、待ち行列に積んで、頼まれた Claude Code on the web のセッションが回す。`NOVEL_CLAUDE_MODE`、`.docs/claude-tasks.md`)

## 構成の決め方

列の定義(`db/schema.py`)、値の型(`Stamp`・`confirmed`)、確定・修正のときの検証(実在確認・別名の制約・
子の行の扱い)はすべて python 側にある。Next.js から db を直接開くと、その全部を
TypeScript にもう一度書くことになり、正が二つになる。そのため API は FastAPI で python 側に置き、
書き込みは `data_access_logic/` の入口(`execute(s)`)を通す。画面は列の情報を
`GET /api/tables` から受け取って組み立てるので、列を足しても画面のコードは変えなくてよい。
型は FastAPI の OpenAPI(`gui/api/openapi.json`)から `gui/web/lib/openapi.d.ts` を生成して合わせる。
画面に出す文言(ボタン・見出し・状態表示など、英語)は `gui/web/lib/text.ts` の `T` に集め、ページ・コンポーネントには直書きしない。
db の値(承認/非承認/未確認、場所の category など)と API から来るテーブル名・列名のラベルは文言ではないので、`T` には置かない。

入口の `run()` ではなく `execute(s)` を呼ぶのは、`run()` が確定のあとに AI(`claude -p`)で
要約・ミーム・検証を作る段を持ち、GUI の一回の操作で待てる長さではないため。その分は
`RefreshGeneratedContent` が後でまとめて拾う。追加・修正の応答は、`execute(s)` が返したレスポンスのモデル
(`*Record`)をそのまま使い、行を読み直さない。行を引く・名前で呼ぶ・当事者を読むといった処理も `data_access_logic` のもの
(`common_query.get_row`・`label.label_of`・`entrypoint.loading`)を使い、API の側には写しを持たない。

## 起動

リポジトリのルートで(環境変数は他の python と同じ。db は `DEM_DATABASE_URL` の RDS で、踏み台越しの転送を先に張っておく。
`.claude/docs/setup.md`)。API と画面を一緒に起こしてブラウザで開くのは `gui.dev`。
`gui/web/node_modules` が無ければ先に `npm install` を回す。VS Code なら タスク `db tunnel` のあとに `app`(`.vscode/tasks.json`)。

```
.venv/bin/python -m gui.dev              # API :8765 + 画面 :3000 を起こし、http://localhost:3000 を開く。Ctrl+C で両方止める
                                          # 片方が落ちてももう片方は止めず、落ちた方だけ自動で再起動する
.venv/bin/python -m gui.dev --no-browser # 開かない。--api-port / --web-port でポートを変える
.venv/bin/python -m gui.dev --browser-only # API・画面はすでに起きている前提で、ブラウザだけ開く
```

ポートが既に使われていれば(前回の起動の残りなど)、それを聞いている処理を止めてから起こす(Linux は `ss`、macOS は `lsof`、
Windows は `netstat` で探す)。止められなければ終了コード 1 で止まる。
`next dev` はビルド先(`gui/web/.next`)ごとに 1 つしか動かせないので、2 つ目を起こすときは環境変数 `NOVEL_WEB_DIST_DIR`
でビルド先を分ける(テスト用は `.next-test`)。

ブラウザは Brave があればそれを使い、プロファイルをリポジトリのルートの `.brave-profile/` に作って
(`--user-data-dir`)開く。普段のプロファイルと分かれるので、GUI 用のタブ・設定だけがそこに残る。
`.brave-profile/` は `.gitignore` に入れてある。Claude Code の SessionStart フック
(`.claude/hooks/session-start.sh`)がセッション開始時にこのディレクトリを用意する
(`gui.dev` 実行時にも無ければ作る)。Brave が無ければ既定のブラウザで開く。

別々に起こすなら次の二つ。

```
.venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload --reload-dir data_access_logic --reload-dir db --reload-dir gui/api   # .py を直すと自動で再起動
(cd gui/web && npm install && npm run dev)     # http://localhost:3000
```

`/api/*` は Next.js の route handler(`gui/web/app/api/[...path]/route.ts`)が `NOVEL_API_URL`(既定 `http://127.0.0.1:8765`)へ流すので、
ブラウザから見ると同じオリジンになる。`NOVEL_API_KEY` があれば、流すときに `x-novel-api-key` を付ける(API 側は `NOVEL_API_KEYS` に呼ぶ側ごとの鍵を
`gui=…,web=…` の形で持ち、どれにも合わない要求を 401 にする。公開の URL に置くとき用。`.docs/aws-deploy.md`)。

## API

| メソッド | パス | 中身 |
| --- | --- | --- |
| GET | `/api/tables` | 扱うテーブルと列の情報(型・必須・選択肢・参照先・子の行) |
| GET | `/api/tables/{table}/records?q=&limit=&offset=&sort=&order=&<列>=<値>` | 一覧。`q` は名前・本文の部分一致、列名の query は等値(`null` で空)。`sort` は並べる列(空の行は後ろ)、`order` は `asc`/`desc`。省くとテーブルの既定(`TableMeta.sort`/`order`。話は開始の降順、ほかは id の降順) |
| GET | `/api/tables/{table}/records/{id}` | 一件。参照先の名前(`labels`)と表示用の関連(`related`)付き |
| POST | `/api/tables/{table}/records` | 追加。確定の入口(`CommitIdea` など)の `execute` を通す |
| PATCH | `/api/tables/{table}/records/{id}` | 修正。渡した欄だけ直す(`UpdateIdea` などの `execute`) |
| GET | `/api/tables/{table}/options?q=` | 参照先を選ぶための id と名前 |
| GET | `/api/review` | 未確認・承認・非承認の件数 |
| GET | `/api/review/{table}/next?after=` | 次の未確認(`after` より後の id。末尾を過ぎたら先頭へ) |
| POST | `/api/review/{table}/{id}` | `{"decision": "承認"/"非承認"/"未確認", "changes": {...}}`。直しと同時に確認を付ける |
| GET | `/api/interface` | 入口の一覧(領域・引数・`claude` を叩くか・db に書くか)と、claude を叩く入口を呼べるか(`claude_available`)・その扱い(`claude_mode`) |
| POST | `/api/interface/{id}` | `{"args": {...}, "background": false}`。`id` は `location.list_locations.ListLocations` のような「領域.ファイル.クラス」。`claude` を叩く入口と `background` は job の id を 202 で返す |
| POST | `/api/tables/{table}/generate/{key}` | 「AI で作成」「AI で補完」。`{"draft": {欄の値}, "args": {…}}`。欄の値(下書き)を核に AI が全欄を組み立て直して行を足す(下書きに `id` があれば、その行の空の本文だけを埋める)入口(`Generate*`)を裏の job で回し、job の id を 202 で返す。生成器の `key` と `args` の欄は `/api/tables` の `generators` にある。Claude Code の環境でだけ(外なら 403) |
| GET | `/api/jobs` / `/api/jobs/{id}` | 裏で走らせた入口の状態・結果・エラー。プロセスの中の job(API を起こしているあいだだけ持つ)と、待ち行列 `ai_task` の行(id は `task-<n>`)の両方 |
| GET | `/api/ping` | 起きているかだけ(`NOVEL_API_KEYS` があっても合言葉なしで通す) |
| GET | `/api/maps` | 星ごとの地図の元データ(星・経緯度を持つ場所・輪郭を持つ場所・色分け)。画面 `/maps` が描く |
| GET | `/api/maps/{planet_id}.svg` | 星ひとつの地図(svg)。場所の座標・領域から python で描く |
| GET | `/api/timeline?since=&until=&story_id=&location_id=` | `since`〜`until` に掛かる話(開始〜終了。終了が空なら開始の一点。開始の無い話は出さない)と出来事(時刻、または開始〜終了)。`story_id` は話だけを、`location_id` はその場所と下位の場所で両方を絞る。それぞれ 500 件まで。画面 `/timeline` が描く |
| GET | `/api/relations` | 人物相関図の元データ(人物・関係)。画面 `/relations` が描く |

`table` は `story` `episode` `character` `character_relation` `event` `location` `idea` `meme` `oracle`。
話(`episode`)はプロット(`plot_text`)と本文(`main_text`)を一緒に扱う。本文の概要(`summary_text`)は画面に出さない。出来事は `character_ids`(当事者)、
人物は足すときだけ `location_id`(出自)を受け取る。
話を足す画面は、作品が決まるとその作品の最後の話(`/api/last_episode`)から場所・視点・登場人物を空の欄にだけ写す。
人物の選択肢(`/api/tables/character/options`)はメインキャラクターを先に並べる。

型を変えたら OpenAPI と TS の型を作り直す。

```
.venv/bin/python -m gui.api.dump_openapi
(cd gui/web && npm run types)
```

## 入口と claude コマンド

`POST /api/interface/{id}` は、入口を組み立てて `run()` を呼ぶ。
`args` の dict は、入口の引数の型注釈が pydantic のモデルなら、そのモデルに一度だけ読み込んでから渡す(`interface.prepare`。読み込めなければ 400。
裏の job にする前に読み込み、job はそのモデルで `interface.call` する)。
どの入口が `claude -p` を回すかは `gui/api/interface.py` が決める(確定のあとに AI を回す `result()` を上書きしている入口、
AI を引数に取る入口)。それらは

- `CLAUDECODE=1` のある環境で起こした API でだけ通す。外なら 403。Claude Code のシェルは `CLAUDECODE=1` を持ち、
  `gui.dev` はどこから起こしても API に渡す(uvicorn を直に起こしたときだけ、自分で渡さなければ止まる)
- 数分〜十数分掛かるので、必ず裏の job にして 202 で id を返す。結果は `/api/jobs/{id}` で引く。job は一度に一つずつ走る
- `NOVEL_CLAUDE_MODE=queue` の API(Lambda)は、その場で回さず待ち行列(`ai_task`)に積んで `task-<n>` を返し、
  Claude Code on the web のセッション(`web_session/run_ai_tasks.py`)が回す。`off` なら 403(`gui/api/claude_env.py`、`.docs/claude-tasks.md`)
- `shared_style_extra` / `style_extra` は渡さない。入口が db の `style_preference`(GUI の「文体の好み」)から読む

## AI で作成 / AI で補完

足す画面(`/tables/<table>/new`)に「AI で作成」のボタンがある。欄に入れた値(全部空でもよい)を下書きとして渡し、
AI が全部の欄を組み立て直して行を足す(入れた値はそのまま残らないことがある)。

本文(`text`。話は `main_text`)が空の行の詳細(編集)画面には「AI で補完」のボタンが出る(本文が埋まっていれば出ない)。その行の
id を渡し、AI がその行の本文だけを書いて埋める(本文以外の欄は変えない)。「AI で作成」と同じ入口(クラス)を、
別のキー・`mode="edit"` の生成器として呼ぶ。

どのテーブルにどのボタンが出るかは `gui/api/generate.py` が決め、`/api/tables` の `generators` に載る。

| テーブル | ボタン | 入口 | 足す画面 | 詳細画面(本文が空のときだけ) |
| --- | --- | --- | --- | --- |
| 人物 | AI で作成 / AI で補完 | `character.generate_character.GenerateCharacter` | 名前・説明(本文 `text` と来歴 `histories` の各行)は核。性別・体格・口調・性格(`parameters`)・種別・生年・没年・メインキャラクターは決まった値。出自(`location_id`)は出身地。`time`(現在の時刻)を省けば世界の最新の出来事の時刻 | 決まっている名前・属性・出自を核に本文(芯)と来歴だけを書く(来歴の節目は今の行に足す) |
| 出来事 | AI で作成 / AI で補完 | `event.generate_event.GenerateEvent` | 名前・本文は場面の指定。時刻・場所・当事者は決まった値(省けば世界の最新・当事者の現在地・居合わせるサブキャラクター) | 名前・場所・当事者から記録の本文だけを書く |
| 話 | AI で枠を作る | `episode.generate_frame.GenerateFrame` | 作品は必須。題・プロット・視点・場所は核、時刻は決まった値(省けば AI が直前の話の後から選ぶ)。登場人物はパネルの `character_ids`(初めは欄の値)。本文は書かない | (出ない。枠のみで足す画面専用) |
| 話 | AI でプロット補完 | `episode.complete_plot.CompletePlot` | 今のプロットを核に、本文全体を場面に割ったプロット(`## 場面` / `## 狙い`)を書き直させ、それでプロットをそっくり置き換える(今のプロットの中身は含めさせる)。書き直したプロットに出るのに登場人物にいない人物は作って(承認済みで)登場人物に足し、話の場所より細かい舞台が要れば作って話の場所にする。本文は書かない。プロットか時刻が空なら先に枠を決める。登場人物は欄の値。本文とモデル・effort を分けるため、自分だけの起動ボタンと欄(`separate`)で出し、注文(今のプロットに加えて新しいプロットに望むこと。行数で高さの変わるマークダウンの欄)・モデル・effort を聞く(既定は opus 5.5 の low) | 本文の無い話のページに出る(その枠のプロットを置き換える)。登場人物はこの話の `episode_character` |
| 話 | AI で本文まで書く | `episode.generate_episode.GenerateEpisode` | プロットと時刻が揃っていればそのまま本文を書く。どちらかが空なら先に枠を決める。登場人物は欄の値(空なら止まる) | 本文の無い話のページに出る(その枠へ書く)。登場人物はこの話の `episode_character`(空なら止まる) |

話の生成・推敲に渡す登場人物は、話と人物のリレーション(`episode_character`。話のページの登場人物のボタン、
足す画面の `character_ids` の欄)だけから取る。枠の生成(`AI で枠を作る`)のパネルの「登場人物」は初めにその値を出し、選び直せば
その人物で生成し、`episode_character` も置き換える。あらすじ・本文の生成はパネルで登場人物を聞かない。本文の生成(`AI で本文まで書く`)は、書く前にプロットで台詞・行動のある人物を AI に挙げさせて登場人物に足し、db にいない人物は作って足す(`data_access_logic/readme.md` の「プロットからの登場人物」)。

claude を叩くので裏の job になり、画面は job を待って、終わったら足した(直した)行のページへ移る(本文なら読み直す)。
生成は他のテーブルにも行を足す(プロット補完が人物・場所を作るなど)ので、終わったら全テーブルの選択肢の取り置きを捨て、
出ている選択欄も読み直す(`ReferenceSelect` の `invalidateAllOptions`)。
参照の選択欄(場所の木の選択を含む)と話の登場人物の並びには、選んだ行のページへのリンク(`RecordLink`)を添える。

## AI で推敲する

本文のある話の詳細画面には「AI で推敲する」も出る(`episode.revise_episode.ReviseEpisode`、`generate.py` では
`panel=True`)。直す指示(`instruction`)を必須で受け取り、指示の箇所だけでなく、指示と材料を総合的に判断して本文を大幅に書き直してよい(話の大筋は保つ)。
登場人物(`character_ids`)は聞かない。登場人物はこの話の `episode_character`
(ページの登場人物のボタンで編集中の値)を使い、空なら止まる。前の話は、この話の時刻より前の話を自動で使う
(直前の五話は本文、それより前は概要)。

上の「AI で作成 / AI で補完」の小さなボタン列(`GeneratePanel`)とは別に、本文を見ながら大きな指示文を
書けるよう専用のパネル(`RevisePanel`)で出す。開くボタンは save の隣(actionbar)に置き、押すと左の欄の
一番下で大半(7 割ほど)を使って開く(本文は右にそのまま残る)。汎用のフィールド一覧(`GeneratePanel` と同じ
組み方)だと参照選択の欄(フィルター付き)が場所を取って指示テキストが埋もれるので、`RevisePanel` は
専用の構成で組む: 指示テキスト(大きなマークダウン欄)・モデル・effort・実行ボタン。タイトル・
プロットは見出しや左の欄に既に出ているので、ここでは繰り返さない。
モデル・effort の選択肢は `AI で本文まで書く` と共通(`ai_client.AVAILABLE_MODELS` / `AVAILABLE_EFFORTS`)。
選んでいなければプルダウンの見た目も既定値(`ColumnMeta.default`)を選んだ状態にする(実際に渡す値は
未選択のままなら省く。既定値を選んだ体裁と、渡さず入口側の既定に任せる動きを揃えている)。

`GeneratorMeta.panel` が true の生成器は `GeneratePanel` には出さず、`RevisePanel` の側だけが拾う
(テーブルごとに一つを想定)。

## 型と lint

```
(cd gui/web && npm run typecheck && npm run lint)
```
