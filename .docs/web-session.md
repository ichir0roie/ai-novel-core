# web のセッション(Claude Code on the web)から db に届く道

待ち行列を回す web のセッション([claude-tasks.md](claude-tasks.md))は、Anthropic のクラウドの VM で動く。
その VM は AWS の db(RDS for PostgreSQL。[aws-deploy.md](aws-deploy.md))に直に繋がない。
db の読み書きは、すべて API(`novel-api` の関数 URL、HTTPS)の段(`/api/steps/{id}`)と入口(`/api/interface/{id}`)を通す(下の「決めた道」)。
Claude 向けの決まりは `.claude/docs/aws.md`。

## 届かない理由

- クラウドのセッションの外向きの通信は、すべて HTTP/HTTPS のプロキシを通る(Claude Code のドキュメントの「Security proxy」)。
  PostgreSQL の通信(5432 の独自の手順)は HTTP ではないので、psycopg で直に繋ぐ道は通らない見込み(このリポジトリでは試していない)
- db は private subnet にあり、公開していない。出口の IP も決まっていないので、セキュリティグループで「web のセッションだけ」に絞ることもできない
- HTTPS だけで SQL を流せる Data API は Aurora にしか無く、RDS のインスタンスには無い
- 手元で使う踏み台越しの道(`tool.aws.rds`)は ssh なので、同じくプロキシを通らない

## 決めた道: API を通す

| | 道 | 判断 |
| --- | --- | --- |
| A(採用) | web のセッションが、db ではなく API(Lambda の関数 URL、HTTPS)を叩く | プロキシを通る。db の鍵を web に置かなくてよい。API が公開するのは決まった段と入口だけなので、web の Claude が誤った指示に従っても、できることはその範囲に収まる |
| B | 自分の VPC に置くセルフホストの環境(`ccpool_…`) | 採らない。組織(Team / Enterprise)向けの機能で、ランナーを動かす費用が掛かる |
| C | db を Aurora Serverless v2 に移し、Data API で繋ぐ | 採らない。費用が増え、RDS のインスタンスを使い回せなくなる |

web のセッションの側のコードは `web_session/` にある(`api.py` が関数 URL を叩く。形は [claude-tasks.md](claude-tasks.md) の「web のセッションで回す」)。

### クラウド環境(claude.ai/code → 環境の設定 → Edit)

db が要る web の作業の専用の環境を作る。ふだんのセッションの環境に API の鍵を置かない。

- Network access: `Custom`。既定の一覧(PyPI・npm など。フックの `uv pip install` に要る)を残し、`novel-api` の関数 URL のホスト
  (`<id>.lambda-url.ap-northeast-1.on.aws`)を足す。
  関数 URL は SSM の `/novel/api/function-url` で見る(`aws ssm get-parameter --name /novel/api/function-url`)。
  このリポジトリは公開なので、実際の URL は文書やコードに書かない
- Environment variables: 次を置く。環境変数はその環境を使う人なら誰でも読めるので、置くのは web 用の合言葉だけにする
  (db のパスワード・AWS のアクセスキーは置かない)

  ```
  NOVEL_API_URL=https://<id>.lambda-url.ap-northeast-1.on.aws
  NOVEL_API_KEY=<web 用の合言葉。SSM の /novel/api-keys/web の値>
  BASH_DEFAULT_TIMEOUT_MS=3600000
  BASH_MAX_TIMEOUT_MS=3600000
  ```

## 確かめる

その環境でセッションを開き、世界リポジトリのルートで:

```
.venv/bin/python -m web_session.check_api
```

API に届いたか・db の種類・alembic の版(db の側と、このセッションのコードの head)・PostGIS の版・待ち行列の件数・
`claude` コマンドの有無を JSON で出す。`connected: true` かつ `alembic_current == alembic_head` なら終了コード 0。
手元から AWS の db の版を確かめるときは `DEM_WORLD_DIR="$PWD" PYTHONPATH=core .venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c core/db/alembic/alembic.ini current`。

| 出たもの | 見るところ |
| --- | --- |
| `api_url_set` が false | 環境の `NOVEL_API_URL` |
| `403` / `host_not_allowed` | 環境の Network access に、`novel-api` の関数 URL のホストが入っているか |
| `401` | 環境の `NOVEL_API_KEY` が、Lambda の `NOVEL_API_KEYS` の `web=` と合っているか |
| `alembic_current` が `alembic_head` と違う | db にマイグレーションを当てる([ci-cd.md](ci-cd.md#マイグレーション))か、`core` を db の版に合わせる |
| `claude_command` が null | web のセッションでは claude が入っている前提。フックの途中で落ちていないか |

環境変数を変えたら、次に開くセッションから効く(開いているセッションには効かない)。

## 守り

- web の環境は専用のものにする。環境変数はその環境を使う人なら誰でも読めるので、ふだんの作業のセッションには db や API の鍵を置かない
- API の合言葉は画面(Amplify)用と web 用で分ける。web 用が漏れたら、それだけを替えるか Lambda から外す。定期的に回す
- 待ち行列を回すスキル(`run-ai-tasks`)は「コマンドを回して報告するだけ・何も直さない」にしてある。
  `ai_task` の中身(画面から積んだ引数)は入口の引数としてだけ使い、指示として読まない
