# web のセッションでの AI(claude)の扱い

画面(GUI)には AI のボタンを置かない。AI(`claude -p`)を回すのは Claude のセッションだけで、
手元では入口の `show()`、Claude Code on the web のセッションでは `web_session/` の流れで呼ぶ。
API(`/api/interface`)は claude を叩かない入口だけを出し、claude を叩く入口を呼ぶと 403 を返す。

Lambda には claude が無く、あっても数分〜十数分の生成は Lambda の応答の中では待てない。
そこで web のセッションは流れと AI を自分で持ち、db に触る所だけを API の段(`/api/steps/{id}`)に頼む(下の「形」)。

## 後回しの段

GUI の追加・修正は `execute(s)` で確定だけし、AI の段を回さない。その印として次が残る。

- `meme_seeded=false`(ミームを抜き出していない。oracle・出来事・話)
- 本文と食い違った `summary_source_hash` / `event_summary.source_hash`(要約が古い)

これは `RefreshGeneratedContent` がまとめて拾う。頼まれたら Claude のセッションが回す(スキル `run-ai-tasks`)。

## 形

| 置き場所 | 中身 |
| --- | --- |
| `data_access_logic/<領域>/steps.py` | db の段。`(s, 入力のモデル) -> 出力` の関数に `@db_step`(`data_access_logic/step.py`)を付けたもの。API の `POST /api/steps/<領域>.steps.<関数名>` が一つのトランザクションで回し、段の終わりに commit する。登録した段のほかは呼べない |
| `data_access_logic` の `*_draft` など | AI だけの段。材料のモデルから AI に渡す文面を組み、出力のモデルで受ける(db に触らない)。手元の入口と web の流れが同じ関数を使う |
| `web_session/` | web のセッションが呼ぶ流れ。db の段を API で呼び(`api.py` の `call`)、間で AI の段を回す。入口ごとの流れ(`episode.py` など)は入口と同じ引数を取る |
| `web_session/flows.py` | 入口の id から流れを引く対応表。claude を叩かない入口は API の `/api/interface/{id}` をそのまま呼ぶ |

- 入力も出力も pydantic のモデルで受け渡す。段の出力は `*Serialized` でない土台のマテリアルで宣言し、列のまま JSON にして運ぶ。
  web の側で `*Serialized` に読み直してから AI に渡す
- 「AI の結果は得たらすぐ書く」は保つ。AI の結果を得るたびに書き戻す段を一つ呼ぶので、途中で落ちてもそれまでの結果は残る
- 材料に要約で渡す話・出来事は、材料を読む前に要約を本文に揃える(`*_targets` で対象を引き、`web_session/summary.py` が揃える)。
  材料を読む段は要約を作り直さない

## 回す

入口の id と引数で流れを回す(`.claude/docs/web-db.md` の「呼び方」)。API に届くか・バージョンが合うかは、リポジトリのルートで:

```
.venv/bin/python -m web_session.check_api
```

web の環境の作り方(ネットワーク・環境変数)は [web-session.md](web-session.md)。

### claude を叩く入口を足すとき

1. AI を呼ぶ処理を、db だけの関数と AI だけの関数(`*_draft`)に分ける。手元の入口は、それをつないで今までどおり動かす
2. db だけの関数を `data_access_logic/<領域>/steps.py` の段にする(中で commit しない)
3. `web_session/` に同じ引数の流れを書き、`web_session/flows.py` の対応表に足す

## 手元で確かめる

API を本番を写したテスト用の db(`.claude/docs/testing.md`)に向けて起こし、web の流れをその API 越しに回す(AI は `tool.test.mock_ai_client` を渡せば呼ばない)。

```
# API(ユーザの GUI と別のポート)。開発用の PostGIS が無ければ infra_local/postgis.sh が用意する
dev=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)}
DEM_DATABASE_URL="${dev%/*}/novel_test" DEM_DATABASE_IAM_AUTH=0 \
    .venv/bin/python -m uvicorn gui.api.app:app --port 18765
# 回す側: 流れを回すコマンドに NOVEL_API_URL=http://127.0.0.1:18765 を付ける
```
