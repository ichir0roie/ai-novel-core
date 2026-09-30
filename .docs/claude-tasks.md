# Web にしたときの AI(claude)の扱い

「AI で作成」「AI で補完」「AI で推敲する」と、`/interface` の claude を叩く入口(✦)は `claude -p`(Claude Code の CLI)を
回す。Lambda には claude が無く、あっても数分〜十数分の生成は Lambda の応答の中では待てない。
そこで、Web では押した操作を db の待ち行列に積むだけにし、ユーザが Claude Code on the web のセッションに
「作業やって」と頼んだときに、そのセッションがまとめて回す(スキル `run-ai-tasks`)。

処理の主体は Claude Code のセッションに置き、Lambda の API は db とのやり取りだけを受け持つ。
セッションは流れと AI(`claude -p`)を自分で持ち、db に触る所だけを API の段(`/api/steps/{id}`)に頼む(下の「web のセッションで回す」)。

## 三つのモード(`NOVEL_CLAUDE_MODE`)

| モード | どこで | ボタン | 押したとき |
| --- | --- | --- | --- |
| `direct` | Claude Code の中(`CLAUDECODE=1`。`gui.dev` を含む) | 押せる | API のプロセスの中で裏の job として回す(今までどおり) |
| `queue` | Lambda(イメージの既定) | 押せる。「待ち行列に積む」旨を出す | `ai_task` に行を積み、202 で `task-<id>` を返す |
| `off` | 上のどちらでもない | 押せない(説明を出す) | 403 |

省けば、Claude Code の中なら `direct`、外なら `off`。`direct` を指定しても Claude Code の外なら `off` に落とす。
画面は `/api/tables` の `claude_available`(押せるか)と `claude_mode` を見て、ボタンの活性・説明・job を見に行く間隔
(direct は 2 秒、queue は 15 秒)を決める。Web でボタンを消したいだけなら `NOVEL_CLAUDE_MODE=off` にする。

`queue` のときは、claude を叩かない入口の `background: true` の呼び出しも行に積む(Lambda は応答を返したあと裏で走り続けられない)。

## 待ち行列とフラグ

AI が要る段は二種類あり、どちらも web のセッションが拾う。

| 種類 | 印 | 例 |
| --- | --- | --- |
| 明示の依頼 | `ai_task` の行(`status=queued`) | 「AI で作成」、推敲、`/interface` の ✦ の入口 |
| 後回しの段 | 各行のフラグ・ハッシュ | GUI の追加・修正は `execute(s)` で確定だけし、AI の段を回さない。その印として `meme_seeded=false`(ミームを抜き出していない)と、本文と食い違った `summary_source_hash` / `event_summary.source_hash`(要約が古い)が残る |

後回しの段は `RefreshGeneratedContent` がまとめて拾う作りなので、印(フラグ)を足さずにそのまま使う。
web のセッションは待ち行列が尽きたらこれを一度回す。

### `ai_task`

| 列 | 中身 |
| --- | --- |
| `entrance` / `args` | 呼ぶ入口(`gui/api/interface.py` の id)と引数(JSON)。積むときに一度 `interface.prepare` に通し、引数の食い違いは 400 で返す |
| `status` | `queued` → `running` → `done` / `failed` |
| `result` / `error` | 入口の結果(JSON)と、落ちた理由 |
| `attempts` | 拾った回数。回すのは一度に一つのセッションだけなので、回し始めに `running` のまま残った行(前のセッションが途中で終わった)を `queued` に戻して拾い直す。3 回で `failed` |

画面の job の一覧(`/api/jobs`)は、プロセスの中の job と `ai_task` の新しい 50 行を並べる。

## web のセッションで回す

### 形

| 置き場所 | 中身 |
| --- | --- |
| `data_access_logic/<領域>/steps.py` | db の段。`(s, 入力のモデル) -> 出力` の関数に `@db_step`(`data_access_logic/step.py`)を付けたもの。API の `POST /api/steps/<領域>.steps.<関数名>` が一つのトランザクションで回し、段の終わりに commit する。登録した段のほかは呼べない |
| `data_access_logic` の `*_draft` など | AI だけの段。材料のモデルから AI に渡す文面を組み、出力のモデルで受ける(db に触らない)。手元の入口と web の流れが同じ関数を使う |
| `web_session/` | web のセッションが呼ぶ流れ。db の段を API で呼び(`api.py` の `call`)、間で AI の段を回す。入口ごとの流れ(`episode.py` など)は入口と同じ引数を取る |
| `web_session/flows.py` | 待ち行列の入口の id から流れを引く対応表。claude を叩かない入口は API の `/api/interface/{id}` をそのまま呼ぶ |

- 入力も出力も pydantic のモデルで受け渡す。段の出力は `*Serialized` でない土台のマテリアルで宣言し、列のまま JSON にして運ぶ。
  web の側で `*Serialized` に読み直してから AI に渡す
- 「AI の結果は得たらすぐ書く」は保つ。AI の結果を得るたびに書き戻す段を一つ呼ぶので、途中で落ちてもそれまでの結果は残る
- 材料に要約で渡す話・出来事は、材料を読む前に要約を本文に揃える(`*_targets` で対象を引き、`web_session/summary.py` が揃える)。
  材料を読む段は要約を作り直さない

### 回す

ユーザが web のセッションで頼んだら、スキル `run-ai-tasks` の手順で回す。世界リポジトリのルートで:

```
.venv/bin/python -m web_session.check_api     # API に届くか・版が合うか
.venv/bin/python -m web_session.run_ai_tasks  # 待ち行列を回す
```

`run_ai_tasks` は次を行い、回した行と残りの件数を JSON で print する。

1. `running` のまま残った行を `queued` に戻す
2. `queued` を古い順に一件ずつ拾い、入口に当たる流れを回して結果を書き戻す(落ちた行は `failed` にして次へ)
3. 尽きたら `RefreshGeneratedContent` に当たる流れを一度回す(`--no-refresh` で外す)

web の環境の作り方(ネットワーク・環境変数)は [web-session.md](web-session.md)。

### claude を叩く入口を足すとき

1. AI を呼ぶ処理を、db だけの関数と AI だけの関数(`*_draft`)に分ける。手元の入口は、それをつないで今までどおり動かす
2. db だけの関数を `data_access_logic/<領域>/steps.py` の段にする(中で commit しない)
3. `web_session/` に同じ引数の流れを書き、`web_session/flows.py` の対応表に足す

## 手元で確かめる

API を `novel.test.db` に向けて起こし、web の流れをその API 越しに回す(AI は `tool.test.mock_ai_client` を渡せば呼ばない)。

```
# API(queue モード。ユーザの GUI と別のポート)
DEM_DB_PATH=$PWD/novel.test.db NOVEL_CLAUDE_MODE=queue .venv/bin/python -m uvicorn gui.api.app:app --port 18765
# 回す側: Claude Code の中で
NOVEL_API_URL=http://127.0.0.1:18765 .venv/bin/python -m web_session.run_ai_tasks
```
