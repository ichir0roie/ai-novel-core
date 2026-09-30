# 自動デプロイ(GitHub → Lambda / Amplify)

| 何を | きっかけ | 仕組み |
| --- | --- | --- |
| API(Lambda) | `main` への push のうち、API が読むコード(`ai/` `data_access_logic/` `db/` `randomizer/` `gui/api/` `requirements.txt` `deploy/lambda/`)が変わったとき。手で回すなら Actions の「Run workflow」 | `.github/workflows/deploy-api.yml` |
| 画面(Amplify) | `main` への push | Amplify が GitHub を見て `amplify.yml` で建てる(GitHub Actions は使わない) |
| db のマイグレーション | 手で | 下の「マイグレーション」 |

## API の流れ

1. `ruff check`(実行時の誤りだけを見る設定。`ruff.toml`)
2. OIDC で AWS のロールを引き受ける(鍵を GitHub に置かない)
3. `deploy/lambda/Dockerfile` を `linux/amd64` で建て、ECR に `<commit の sha>` の tag で push
   (`--provenance=false`。Lambda は複数アーキの目録を受け付けない)
4. `aws lambda update-function-code` → 反映を待つ
5. `API_BASE_URL` があれば `/api/ping` を叩いて確かめる

リポジトリの変数(Settings → Secrets and variables → Actions → **Variables**)が無ければ、ジョブは飛ばされる
(このリポジトリは公開なので、フォークや設定前に落ちないようにしている)。秘密は置かない。

| 変数 | 例 |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/github-ai-novel-core-deploy` |
| `AWS_REGION` | `ap-northeast-1` |
| `ECR_REPOSITORY` | `novel-api` |
| `LAMBDA_FUNCTION_NAME` | `novel-api` |
| `API_BASE_URL` | Lambda の関数 URL(任意。煙の確かめ用) |

## AWS 側の用意(一度だけ)

1. IAM の ID プロバイダに GitHub の OIDC(`token.actions.githubusercontent.com`、対象 `sts.amazonaws.com`)を足す
2. デプロイ用のロールを作る。信頼ポリシーは **このリポジトリの main だけ** に絞る(公開リポジトリなので、
   PR やフォークから引き受けられないようにする)

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": { "Federated": "arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com" },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": {
           "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
           "token.actions.githubusercontent.com:sub": "repo:ichir0roie/ai-novel-core:ref:refs/heads/main"
         }
       }
     }]
   }
   ```

3. 権限は ECR への push と、その関数の更新だけ

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
       { "Effect": "Allow",
         "Action": ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
                    "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart"],
         "Resource": "arn:aws:ecr:<region>:<account>:repository/novel-api" },
       { "Effect": "Allow", "Action": ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"],
         "Resource": "arn:aws:lambda:<region>:<account>:function:novel-api" }
     ]
   }
   ```

4. ECR のライフサイクルポリシーで、古いイメージを数十個残して消す

## マイグレーション

コードと db の形は揃えて出す必要がある。列を足す変更は **db を先に、コードを後に** 出す(古いコードは新しい列を知らないだけで動く)。
列を消す・名前を変える変更は、コードを先に消す側へ直してから db を変える。

PostgreSQL へは、作業する端末から `DEM_DATABASE_URL` を渡して当てる。

```
export DEM_DATABASE_URL='postgresql+psycopg://…'        # B: 一時的に繋げるようにして
# export DEM_DATABASE_URL='postgresql+auroradataapi://:@/novel' AURORA_CLUSTER_ARN=… AURORA_SECRET_ARN=…   # A: Data API
.venv/bin/python -m alembic -c core/db/alembic/alembic.ini current
.venv/bin/python -m alembic -c core/db/alembic/alembic.ini upgrade head
```

GitHub Actions からは当てない(db への道をワークフローに開けたくない・マイグレーションは中身を見てから当てたい)。
当て忘れはルーチンの `tool.routine.check_db` が版の食い違いとして報告する。

## 画面(Amplify)

- Amplify のアプリを `main` に繋ぐと、push のたびに `amplify.yml` で建て直す。建て直しの対象を `gui/web` の変更だけに
  絞るなら、Amplify の「ビルドの設定」でモノレポのアプリのパスを `gui/web` にしておく(`AMPLIFY_MONOREPO_APP_ROOT`)
- 型(`gui/web/lib/openapi.d.ts`)は API の OpenAPI から作ってコミットしてあるので、Amplify のビルドは python を要らない
- 画面と API の組み合わせがずれる(新しい画面が古い API を呼ぶ)ことがある。API を変えた PR は、Lambda の反映
  (数分)を待ってから画面が出るよう、API の変更を先に `main` へ入れるか、互換を保つ形にする
