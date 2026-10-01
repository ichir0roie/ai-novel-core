# 手元からの db(`CLAUDE_CODE_REMOTE` が `true` でない)

db は AWS の RDS(PostgreSQL + PostGIS)ただ一つ。手元の作業も、画面(Amplify)と web のセッションと同じ db を読み書きする。
ここは手元で db に直に繋ぐときの決まり。web のセッションは db に繋がないので、代わりに `.claude/docs/web-db.md` を読む。
ユーザは `gui/` の GUI(FastAPI + Next.js。起動は `gui/readme.md`)で見て直す(ページは `/tables/<table>/<id>`)。
Claude は入口越しに db だけで作業を完結させ、報告は db を読んで行う。

## 手元からの道

SessionStart フックが、踏み台越しの転送(`tool.aws.rds --serve`、127.0.0.1:15432)を裏で起こし、次の環境変数を渡す。
python はリポジトリのルートの `.venv/bin/python` で呼べば、そのまま RDS を読み書きする。

| 環境変数 | 値 |
| --- | --- |
| `DEM_DATABASE_URL` | `postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require` |
| `DEM_DATABASE_IAM_AUTH` | `1`(パスワードの代わりに IAM データベース認証のトークンで繋ぐ。パスワードはどこにも置かない) |

- `novel_app` は行の読み書き(DML)だけができる。表を作る・変える(DDL)ことはできない
- `connection refused` で落ちたら、転送がまだ張れていない(踏み台が止まっていれば起こすのに 1 分ほどかかる)か、落ちている。
  `.cache/rds-tunnel.log` を見て、無ければ `.venv/bin/python -m tool.aws.rds --serve` を `run_in_background` で起こす
- 転送は EC2 Instance Connect Endpoint の都合で 1 時間ごとに切れ、`--serve` が張り直す。その間に落ちた処理はやり直す
- 止めるのは `pkill -f 'tool.aws.rds --serve'`(自分で起こした踏み台も止まる)。ユーザに頼まれたときだけ止める

## 読み書きの決まり

- コードから触るときは `from db.schema import get_env_session` で `Session` を開く。`engine` も同じモジュールにある
- 作業として db を読み書きするときは `data_access_logic/` の入口越しに、既存の python コードを呼んで行う
- `data_access_logic/readme.md` を操作前のマニュアルとする。操作の前にその「依頼内容 → 呼ぶコード」の
  対応表を引き、依頼に当たる入口を呼ぶ
- 対応する入口が無ければ、readme の「作り方」に沿って入口を新しく作ってから行う。
  足したら同じ作業のうちに readme の対応表へ行を足す(表に無い入口は次から見えない)
- 読み取り(`select`)だけなら入口を通さなくてよい。SQLAlchemy で好きに覗いてよい。
  書き込み(`insert` `update` `delete`)は必ず入口越しに行う
- 調査用の読み取り例:

```
.venv/bin/python -c "
from sqlalchemy import text
from db.schema import engine
with engine.connect() as c:
    print(c.execute(text('select count(*) from character')).scalar())
"
```

## マイグレーションの確認

db の版は、コードの版(`alembic heads`)と揃っていなければならない。`core` の変更で列が増えていると、db を読む入口が
`column ... does not exist` で止まる。RDS へは `main` へのマージで CI が当てるので、まだマージしていないブランチのマイグレーションは
RDS に無い。db を触る作業の前に食い違いを見つけたら、ユーザに伝える(手で当てるのはユーザに言われてから。`.claude/docs/aws.md` の決まり 1)。

```
.venv/bin/python -m alembic -c db/alembic/alembic.ini current   # novel_app でも版は読める
.venv/bin/python -m alembic -c db/alembic/alembic.ini heads
```

手で当てるときは表を変えるので、同じ転送のまま、表の持ち主の `novel_migrator` に IAM 認証で入って流す(URL のユーザ名だけを替える。downgrade も同じ):
`DEM_DATABASE_URL='postgresql+psycopg://novel_migrator@127.0.0.1:15432/novel?sslmode=require' .venv/bin/python -m alembic -c db/alembic/alembic.ini upgrade head`

## 他のセッションとの同時作業

RDS は、画面・web のセッション・他の Claude Code セッションと共有している。入口越しの書き込みは、他が作業中でもしてよい
(PostgreSQL が行ごとに順を付ける)。同じ行を同時に直すと後の書き込みが勝つので、同じ話・人物を別のセッションが
触っていそうなら、書く前に読み直す。
