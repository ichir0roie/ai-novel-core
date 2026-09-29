# gui — データ編集 GUI

`novel.db` をブラウザから見て直すための道具。API(`gui/api`、FastAPI)と画面(`gui/web`、Next.js)の二つ。

- 未確認のアイデア・ミームを一件ずつ出し、直しながら「承認」「非承認」を付けて次へ進むレビュー画面
- 本文を持つテーブル(作品・話・人物・人物相関・出来事・場所・アイデア・ミーム・覚え書き)の一覧・表示・修正・追加
- 作品の一覧(`/tables/story`)は既定で、場所の木(`parent_id`)に作品(`place_id`、無ければ `world_id`)をぶら下げたツリー。
  場所・作品・話の一覧 API を引いてブラウザ側で組む(`gui/web/lib/storyTree.ts`)。`?view=list` で表に切り替える。
  枝の開閉はブラウザの localStorage に覚える(`gui/web/lib/treeOpen.ts`。既定は開いた状態)
- 星ごとの地図(`/maps`)と人物相関図(`/relations`)。元データは `/api/maps` `/api/relations`。ナビには出さず、
  場所の詳細から `/maps?location=<id>`(その場所を中心に置いて描く)へ、人物の詳細から `/relations?character=<id>`
  (その人物に関わる関係だけを描く)へ飛ぶ
- `data_access_logic/` の入口を画面(`/interface`)と API(`/api/interface`)から呼ぶ。
  `claude` コマンドを叩くものは Claude Code の環境(`CLAUDECODE=1`)で起こした API でだけ、裏の job として走る

## 構成の決め方

列の定義(`db/schema.py`)、値の型(`Stamp`・`confirmed`)、確定・修正のときの検証(実在確認・別名の制約・
子の行の扱い)はすべて python 側にある。Next.js から SQLite を直接開くと、その全部を
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

世界リポジトリのルートで(環境変数は他の python と同じ)。API と画面を一緒に起こしてブラウザで開くのは `gui.dev`。
`gui/web/node_modules` が無ければ先に `npm install` を回す。VS Code なら タスク `gui`(世界リポジトリの `.vscode/tasks.json`)。

```
export DEM_WORLD_DIR="$PWD" PYTHONPATH="$PWD/core"
.venv/bin/python -m gui.dev              # API :8765 + 画面 :3000 を起こし、http://localhost:3000 を開く。Ctrl+C で両方止める
                                          # 片方が落ちてももう片方は止めず、落ちた方だけ自動で再起動する
.venv/bin/python -m gui.dev --no-browser # 開かない。--api-port / --web-port でポートを変える
.venv/bin/python -m gui.dev --browser-only # API・画面はすでに起きている前提で、ブラウザだけ開く
```

ポートが既に使われていれば(前回の起動の残りなど)、それを聞いている処理を止めてから起こす(Linux は `ss`、macOS は `lsof`、
Windows は `netstat` で探す)。止められなければ終了コード 1 で止まる。
`next dev` はビルド先(`gui/web/.next`)ごとに 1 つしか動かせないので、2 つ目を起こすときは環境変数 `NOVEL_WEB_DIST_DIR`
でビルド先を分ける(テスト用は `.next-test`)。

ブラウザは Brave があればそれを使い、プロファイルを世界リポジトリのルートの `.brave-profile/` に作って
(`--user-data-dir`)開く。普段のプロファイルと分かれるので、GUI 用のタブ・設定だけがそこに残る。
`.brave-profile/` は世界リポジトリの `.gitignore` に入れておく。Claude Code の SessionStart フック
(`.claude/hooks/session-start.sh`)がセッション開始時にこのディレクトリを用意する
(`gui.dev` 実行時にも無ければ作る)。Brave が無ければ既定のブラウザで開く。

別々に起こすなら次の二つ。

```
.venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload --reload-dir core   # core/ の .py を直すと自動で再起動
(cd core/gui/web && npm install && npm run dev)     # http://localhost:3000
```

`/api/*` は Next.js が `NOVEL_API_URL`(既定 `http://127.0.0.1:8765`)へ流すので、ブラウザから見ると同じオリジンになる。

## API

| メソッド | パス | 中身 |
| --- | --- | --- |
| GET | `/api/tables` | 扱うテーブルと列の情報(型・必須・選択肢・参照先・子の行) |
| GET | `/api/tables/{table}/records?q=&limit=&offset=&sort=&order=&<列>=<値>` | 一覧。`q` は名前・本文の部分一致、列名の query は等値(`null` で空)。`sort` は並べる列(空の行は後ろ)、`order` は `asc`/`desc`。省くとテーブルの既定(`TableMeta.sort`/`order`。話は開始の昇順、ほかは id の降順) |
| GET | `/api/tables/{table}/records/{id}` | 一件。参照先の名前(`labels`)と表示用の関連(`related`)付き |
| POST | `/api/tables/{table}/records` | 追加。確定の入口(`CommitIdea` など)の `execute` を通す |
| PATCH | `/api/tables/{table}/records/{id}` | 修正。渡した欄だけ直す(`UpdateIdea` などの `execute`) |
| GET | `/api/tables/{table}/options?q=` | 参照先を選ぶための id と名前 |
| GET | `/api/review` | 未確認・承認・非承認の件数 |
| GET | `/api/review/{table}/next?after=` | 次の未確認(`after` より後の id。末尾を過ぎたら先頭へ) |
| POST | `/api/review/{table}/{id}` | `{"decision": "承認"/"非承認"/"未確認", "changes": {...}}`。直しと同時に確認を付ける |
| GET | `/api/interface` | 入口の一覧(領域・引数・`claude` を叩くか・db に書くか)と、この API が Claude Code の環境かどうか |
| POST | `/api/interface/{id}` | `{"args": {...}, "background": false}`。`id` は `location.list_places.ListPlaces` のような「領域.ファイル.クラス」。`claude` を叩く入口と `background` は job の id を 202 で返す |
| POST | `/api/tables/{table}/generate/{key}` | 「AI で作成」「AI で補完」。`{"draft": {欄の値}, "args": {…}}`。欄の値(下書き)を核に AI が全欄を組み立て直して行を足す(下書きに `id` があれば、その行の空の本文だけを埋める)入口(`Generate*`)を裏の job で回し、job の id を 202 で返す。`key` と `args` の欄は `/api/tables` の `generators` にある。Claude Code の環境でだけ(外なら 403) |
| GET | `/api/jobs` / `/api/jobs/{id}` | 裏で走らせた入口の状態・結果・エラー(API を起こしているあいだだけ持つ) |
| GET | `/api/maps` | 星ごとの地図の元データ(星・経緯度を持つ場所・輪郭を持つ場所・色分け)。画面 `/maps` が描く |
| GET | `/api/maps/{planet_id}.svg` | 星ひとつの地図(svg)。場所の座標・領域から python で描く |
| GET | `/api/relations` | 人物相関図の元データ(人物・関係)。画面 `/relations` が描く |

`table` は `story` `episode` `character` `character_relation` `event` `location` `idea` `meme` `oracle`。
話(`episode`)は枠(`key`)と本文(`text`)を一緒に扱う。出来事は `character_ids`(当事者)、
人物は足すときだけ `place_id`(出自)を受け取る。

型を変えたら OpenAPI と TS の型を作り直す。

```
.venv/bin/python -m gui.api.dump_openapi
(cd core/gui/web && npm run types)
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
- `shared_style_extra` / `style_extra` は渡さない。入口が世界リポジトリの `instructions/style.py` から読む(`data_access_logic/world_style.py`)

## AI で作成 / AI で補完

足す画面(`/tables/<table>/new`)に「AI で作成」のボタンがある。欄に入れた値(全部空でもよい)を下書きとして渡し、
AI が全部の欄を組み立て直して行を足す(入れた値はそのまま残らないことがある)。

本文(`text`)が空の行の詳細(編集)画面には「AI で補完」のボタンが出る(本文が埋まっていれば出ない)。その行の
id を渡し、AI がその行の本文だけを書いて埋める(本文以外の欄は変えない)。「AI で作成」と同じ入口(クラス)を、
別のキー・`mode="edit"` の生成器として呼ぶ。

どのテーブルにどのボタンが出るかは `gui/api/generate.py` が決め、`/api/tables` の `generators` に載る。

| テーブル | ボタン | 入口 | 足す画面 | 詳細画面(本文が空のときだけ) |
| --- | --- | --- | --- | --- |
| 人物 | AI で作成 / AI で補完 | `character.generate_character.GenerateCharacter` | 名前・説明は核。性別・体格・口調・性格(`parameters`)・種別・生年・没年・メインキャラクターは決まった値。出自(`place_id`)は出身地。`time`(現在の時刻)を省けば世界の最新の出来事の時刻 | 決まっている名前・属性・出自を核に本文だけを書く |
| 出来事 | AI で作成 / AI で補完 | `event.generate_event.GenerateEvent` | 名前・本文は場面の指定。時刻・場所・当事者は決まった値(省けば世界の最新・当事者の現在地・居合わせるサブキャラクター) | 記録・当事者・関連する設定から小説の本文だけを書く |
| 話 | AI で枠を作る | `episode.generate_frame.GenerateFrame` | 作品は必須。題・種・視点・場所は核、時刻は決まった値(省けば AI が直前の話の後から選ぶ)。登場人物はパネルの `character_ids`(初めは欄の値)。本文は書かない | (出ない。枠のみで足す画面専用) |
| 話 | AI で本文まで書く | `episode.generate_episode.GenerateEpisode` | 種と時刻が揃っていればそのまま本文を書く。どちらかが空なら先に枠を決める。登場人物はパネルの `character_ids`(初めは欄の値。空なら止まる) | 本文の無い話のページに出る(その枠へ書く)。登場人物はパネルの `character_ids`(初めはこの話の `episode_character`。空なら止まる) |

話の生成・推敲に渡す登場人物は、話と人物のリレーション(`episode_character`。話のページの登場人物のボタン、
足す画面の `character_ids` の欄)だけから取る。生成パネルの「登場人物」は初めにその値を出し、選び直せば
その人物で生成し、`episode_character` も置き換える。時刻・場所から人物を拾う既定(その時刻に生きているメインキャラクターなど)は持たない。

claude を叩くので裏の job になり、画面は job を待って、終わったら足した(直した)行のページへ移る(本文なら読み直す)。

## AI で推敲する

本文のある話の詳細画面には「AI で推敲する」も出る(`episode.revise_episode.ReviseEpisode`、`generate.py` では
`panel=True`)。直す指示(`instruction`)を必須で受け取り、筋は変えず指示にある観点だけを直す。
登場人物(`character_ids`)は聞かない。登場人物はこの話の `episode_character`
(ページの登場人物のボタンで編集中の値)を使い、空なら止まる。直前の話は、この話の時刻より前で概要のある三話を
自動で使う。

上の「AI で作成 / AI で補完」の小さなボタン列(`GeneratePanel`)とは別に、本文を見ながら大きな指示文を
書けるよう専用のパネル(`RevisePanel`)で出す。開くボタンは save の隣(actionbar)に置き、押すと左の欄の
一番下で大半(7 割ほど)を使って開く(本文は右にそのまま残る)。汎用のフィールド一覧(`GeneratePanel` と同じ
組み方)だと参照選択の欄(フィルター付き)が場所を取って指示テキストが埋もれるので、`RevisePanel` は
専用の構成で組む: 指示テキスト(大きなマークダウン欄)・モデル・effort・実行ボタン。タイトル・
キーテキストは見出しや左の欄に既に出ているので、ここでは繰り返さない。
モデル・effort の選択肢は `AI で本文まで書く` と共通(`ai_client.AVAILABLE_MODELS` / `AVAILABLE_EFFORTS`)。
選んでいなければプルダウンの見た目も既定値(`ColumnMeta.default`)を選んだ状態にする(実際に渡す値は
未選択のままなら省く。既定値を選んだ体裁と、渡さず入口側の既定に任せる動きを揃えている)。

`GeneratorMeta.panel` が true の生成器は `GeneratePanel` には出さず、`RevisePanel` の側だけが拾う
(テーブルごとに一つを想定)。

## 型と lint

```
(cd core/gui/web && npm run typecheck && npm run lint)
```
