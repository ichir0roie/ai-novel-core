# gui — データ編集 GUI

db(RDS)をブラウザから見て直すための道具。API(`gui/api`、FastAPI)と画面(`gui/web`、Next.js)の二つ。

- 本文を持つテーブル(作品・話・人物・人物相関・出来事・場所・アイデア・ミーム・覚え書き・文体の好み)の一覧・表示・修正・追加
- 作品の一覧(`/tables/story`)は既定で、作品の親子(`parent_story_id`)の木。行の Move ボタンで移動モードに入り、親にする作品をクリックして付け替える。
  作品・話の一覧 API を引いてブラウザ側で組む(`gui/web/lib/storyTree.ts`)。兄弟は、その作品と子孫の作品の一番早い話の順(話の無い作品は後ろ)。`?view=list` で表に切り替える。
  枝の開閉はブラウザの localStorage に覚える(`gui/web/lib/treeOpen.ts`。既定は開いた状態)
- 星ごとの地図(`/maps`)と人物相関図(`/relations`)。元データは `/api/maps` `/api/relations`。ナビには出さず、
  場所の詳細から `/maps?location=<id>`(その場所を中心に置いて描く)へ、人物の詳細から `/relations?character=<id>`
  (その人物に関わる関係だけを描く)へ飛ぶ
- タイムライン(`/timeline?at=<時刻>&span=<日数>&story_id=&location_id=`)。全期間の話を作品ごとの段に分け、
  日の単位の一本の軸に並べる(同じ日の札はその日の位置に時刻の順で縦に積み、期間はその日の始めから終わりの日の終わりまでの帯にする。
  札は名前の幅(上限 960px)まで段を取るので、名前は次の札に切られない)。出来事は出さない。
  段は木にする。作品の段は親の作品(`parent_story_id`)の下に置き、話の無い祖先の作品も段に出す(作品は `/api/tables/story/records` から全部引く)。
  兄弟の作品の段は、その作品と子孫の作品の一番早い話の順に並べ、話の無い作品は一番下に回す。
  段の名前の ▸ / ▾ で開閉する。子の無い段(章の作品など)も閉じられる。閉じた段は一行に縮め、
  子孫の札もまとめて名前の無い印で置く(かざすと中身、クリックで編集。開閉はブラウザの localStorage に覚える)。
  開いた作品の段の下には空の行を一つ空けておき、話を足すときにクリックできるようにする。
  元データは `/api/timeline`(全期間を一度に引く)。軸は一つの欄で横にスクロールする(スクロールバー・ホイール・Earlier / Later。
  段の名前の上のホイールと Shift のホイールは縦)。`span` は画面の幅に収める日数で縮尺を決め、`at` は画面の真ん中の時刻
  (スクロールが止まると書き換わり、入力欄で変えるとそこへスクロールする)。話の無い広い区間は斜線の帯に詰める(目盛りの欄に詰めた長さを出す)。
  目盛りは札の開始日ごとの縦の線で、文字はその年(同じ年が続けば最初の一つだけ)。
  札を横へドラッグすると、その日数だけ日付をずらして保存する(時・分・秒はそのまま。開始・終了を同じだけ動かし、
  手で直したのと同じく同期フラグが外れる)。札のクリックで編集、空の所のクリックで話を足すモーダル(`RecordModal`)を開く
  (押した時刻・段の作品を初期値にする)。`at` を省けば最後の話の時刻を中心にする。
  絞り込み(`span`・`story_id`・`location_id`)は変えるたびにブラウザの localStorage に覚え、どれも付けずに開いたとき(ナビのリンクなど)は覚えた絞り込みに戻す
- `data_access_logic/` の入口を画面(`/interface`)と API(`/api/interface`)から呼ぶ。
  `claude` コマンドを叩く入口は出さず、呼んでも 403 にする(AI は Claude のセッションが回す。`.docs/claude-tasks.md`)
- 参照の選択欄(場所の木の選択を含む)と話の登場人物の並びには、選んだ行のページへのリンク(`RecordLink`)を添える

## 構成の決め方

列の定義(`db/schema.py`)、値の型(`Stamp`)、確定・修正のときの検証(実在確認・別名の制約・
子の行の扱い)はすべて python 側にある。Next.js から db を直接開くと、その全部を
TypeScript にもう一度書くことになり、正が二つになる。そのため API は FastAPI で python 側に置き、
書き込みは `data_access_logic/` の入口(`execute(s)`)を通す。画面は列の情報を
`GET /api/tables` から受け取って組み立てるので、列を足しても画面のコードは変えなくてよい。
型は FastAPI の OpenAPI(`gui/api/openapi.json`)から `gui/web/lib/openapi.d.ts` を生成して合わせる。
画面に出す文言(ボタン・見出し・状態表示など、英語)は `gui/web/lib/text.ts` の `T` に集め、ページ・コンポーネントには直書きしない。
テーブル・列・子リストは日本語の見出しを持たず、物理名(テーブル名・列名)のまま出す。db の値(場所の category など)と物理名は文言ではないので、`T` には置かない。

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
| GET | `/api/interface` | claude を叩かない入口の一覧(領域・引数・db に書くか) |
| POST | `/api/interface/{id}` | `{"args": {...}}`。`id` は `location.list_locations.ListLocations` のような「領域.ファイル.クラス」。`claude` を叩く入口は 403 |
| GET | `/api/ping` | 起きているかだけ(`NOVEL_API_KEYS` があっても合言葉なしで通す) |
| GET | `/api/maps` | 星ごとの地図の元データ(星・経緯度を持つ場所・輪郭を持つ場所・色分け)。画面 `/maps` が描く |
| GET | `/api/maps/{planet_id}.svg` | 星ひとつの地図(svg)。場所の座標・領域から python で描く |
| GET | `/api/timeline?story_id=&location_id=` | 全期間の話(開始〜終了。終了が空なら開始の一点。開始の無い話は出さない)。`story_id` はその作品で、`location_id` はその場所と下位の場所で絞る。画面 `/timeline` が描く |
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
`args` の dict は、入口の引数の型注釈が pydantic のモデルなら、そのモデルに一度だけ読み込んでから渡す(`interface.prepare`。読み込めなければ 400)。
どの入口が `claude -p` を回すかは `gui/api/interface.py` が決める(確定のあとに AI を回す `result()` を上書きしている入口、
AI を引数に取る入口)。それらは API の一覧に出さず、呼んでも 403 にする。
Claude のセッションが、手元は `show()`(`.claude/docs/db.md`)、web は `web_session/flows.py` の `run`(`.claude/docs/web-db.md`)で呼ぶ。

## 型と lint

```
(cd gui/web && npm run typecheck && npm run lint)
```
