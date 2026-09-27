# gui — データ編集 GUI

`novel.db` をブラウザから見て直すための道具。API(`gui/api`、FastAPI)と画面(`gui/web`、Next.js)の二つ。

- 未確認のアイデア・ミームを一件ずつ出し、直しながら「承認」「非承認」を付けて次へ進むレビュー画面
- 本文を持つテーブル(作品・話・人物・人物相関・出来事・場所・アイデア・ミーム・覚え書き)の一覧・表示・修正・追加
- 星ごとの地図と人物相関図(`/api/maps` `/api/relations`)

## 構成の決め方

列の定義(`db/schema.py`)、値の型(`Stamp`・`confirmed`)、確定・修正のときの検証(実在確認・別名の制約・
子の行の扱い)はすべて python 側にある。Next.js から SQLite を直接開くと、その全部を
TypeScript にもう一度書くことになり、正が二つになる。そのため API は FastAPI で python 側に置き、
書き込みは `ai/claude_code/interface/` の入口(`execute(session)`)を通す。画面は列の情報を
`GET /api/tables` から受け取って組み立てるので、列を足しても画面のコードは変えなくてよい。
型は FastAPI の OpenAPI(`gui/api/openapi.json`)から `gui/web/lib/openapi.d.ts` を生成して合わせる。

入口の `run()` ではなく `execute(session)` を呼ぶのは、`run()` が確定のあとに AI(`claude -p`)で
要約・ミーム・検証を作る段を持ち、GUI の一回の操作で待てる長さではないため。その分は
`RefreshGeneratedContent` が後でまとめて拾う。

## 起動

世界リポジトリのルートで(環境変数は他の python と同じ)。

```
export DEM_WORLD_DIR="$PWD" PYTHONPATH="$PWD/core"
.venv/bin/python -m uvicorn gui.api.app:app --port 8765 --reload
```

別のターミナルで画面を起動する(初回は `npm install`)。

```
cd core/gui/web
npm install
npm run dev          # http://localhost:3000
```

`/api/*` は Next.js が `NOVEL_API_URL`(既定 `http://127.0.0.1:8765`)へ流すので、ブラウザから見ると同じオリジンになる。

## API

| メソッド | パス | 中身 |
| --- | --- | --- |
| GET | `/api/tables` | 扱うテーブルと列の情報(型・必須・選択肢・参照先・子の行) |
| GET | `/api/tables/{table}/records?q=&limit=&offset=&order=&<列>=<値>` | 一覧。`q` は名前・本文の部分一致、列名の query は等値(`null` で空) |
| GET | `/api/tables/{table}/records/{id}` | 一件。参照先の名前(`labels`)と表示用の関連(`related`)付き |
| POST | `/api/tables/{table}/records` | 追加。確定の入口(`CommitIdea` など)の `execute` を通す |
| PATCH | `/api/tables/{table}/records/{id}` | 修正。渡した欄だけ直す(`UpdateIdea` などの `execute`) |
| GET | `/api/tables/{table}/options?q=` | 参照先を選ぶための id と名前 |
| GET | `/api/review` | 未確認・承認・非承認の件数 |
| GET | `/api/review/{table}/next?after=` | 次の未確認(`after` より後の id。末尾を過ぎたら先頭へ) |
| POST | `/api/review/{table}/{id}` | `{"decision": "承認"/"非承認"/"未確認", "changes": {...}}`。直しと同時に確認を付ける |
| GET | `/api/maps` / `/api/maps/{planet_id}.svg` | 星ごとの地図(html / svg)。場所の座標・領域から描く |
| GET | `/api/relations` | 人物相関図(html) |

`table` は `story` `plot` `character` `character_relation` `event` `location` `idea` `meme` `oracle`。
話(`plot`)は本文(`episode`)を `text` として一緒に扱う。出来事は `character_ids`(当事者)、
人物は足すときだけ `place_id`(出自)を受け取る。

型を変えたら OpenAPI と TS の型を作り直す。

```
.venv/bin/python -m gui.api.dump_openapi
(cd core/gui/web && npm run types)
```

## テスト

```
.venv/bin/python -m pytest core/tests/test_gui_api.py core/tests/test_confirm_status.py
(cd core/gui/web && npm run typecheck && npm run lint)
```
