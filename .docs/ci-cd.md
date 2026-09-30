# 自動デプロイ(GitHub → Lambda / Amplify)

| 何を | きっかけ | 仕組み |
| --- | --- | --- |
| API(Lambda) | `main` への push のうち、API が読むコード(`ai/` `data_access_logic/` `db/` `randomizer/` `gui/api/` `requirements.txt` `infra/lambda/`)が変わったとき。手で回すなら Actions の「Run workflow」 | `.github/workflows/deploy-api.yml` |
| 画面(Amplify) | `main` への push | Amplify が GitHub を見て `amplify.yml` で建てる(GitHub Actions は使わない) |
| db のマイグレーション | 手で | 下の「マイグレーション」 |

## API の流れ

1. `ruff check`(実行時の誤りだけを見る設定。`ruff.toml`)
2. OIDC で AWS のロールを引き受ける(鍵を GitHub に置かない)
3. `infra/lambda/Dockerfile` を `linux/amd64` で建て、ECR に `<commit の sha>` と `main` の二つの tag で push
   (`--provenance=false`。Lambda は複数アーキの目録を受け付けない)
4. `aws lambda update-function-code`(`<commit の sha>` の tag)→ 反映を待つ
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

## CDK との分担

関数は `infra/` の CDK(`NovelApi`)で持つが、関数のコード(イメージ)だけは CI が差し替える。

| 持ち主 | 持つもの |
| --- | --- |
| CDK(手元から `cdk deploy`) | ECR リポジトリ `novel-api`(ライフサイクルで新しい 30 個を残す)、関数の設定(環境変数・VPC・実行ロール・関数 URL)、GitHub Actions の OIDC のロール |
| CI(`deploy-api.yml`) | イメージを建てて push し、関数のコードを差し替える |

- CDK は関数を `novel-api:main` のイメージで作り、自分ではイメージを建てない。`cdk deploy` は template の `ImageUri` が変わらない限りコードに触れないので、
  CI が差し替えたイメージは、そのあとの `cdk deploy` でも戻らない。関数を作り直すことになっても、その時点の `main` の tag(一番新しいイメージ)を使う
- CI からは `cdk deploy` を流さない。このリポジトリは公開なので、CI の権限を ECR への push とその関数のコードの差し替えだけに絞る。
  `cdk deploy` を CI に許すと、CDK の bootstrap の実行ロール(既定で管理者の権限)を通してアカウントを何でも変えられるようになり、
  synth のときに読む API の合言葉(SSM の SecureString)も CI に渡すことになる
- 最初の一回は、関数を作る前に手元で建てて `main` の tag で push する(関数が無いと、CI の `update-function-code` が落ちる)。
  順番は、ECR を deploy → 手元で push → 関数を deploy

## AWS 側の用意(一度だけ)

ECR・OIDC・CI のロールは手で作らず、`infra/` の `NovelCi` スタック(`infra/lib/ci-stack.ts`)で作る。

1. `core/infra` で `npx cdk deploy NovelCi`
2. 出力の `DeployRoleArn` を、リポジトリの変数 `AWS_DEPLOY_ROLE_ARN` に置く

`NovelCi` が作るもの:

| リソース | 中身 |
| --- | --- |
| ECR リポジトリ `novel-api` | tag の無いイメージは push から 1 日で消し、残りは新しい 30 個を残す。スタックを消してもリポジトリは残す |
| GitHub の OIDC プロバイダ | `token.actions.githubusercontent.com`、対象 `sts.amazonaws.com` |
| CI のロール | 信頼は、SSM の `/novel/deploy/config` に書いた自分の core のリポジトリの `main` だけ(`repo:<owner>/<repo>:ref:refs/heads/main`。公開リポジトリなので、PR やフォークから引き受けられないようにする)。権限は `novel-api` の ECR への push と、関数 `novel-api` の `UpdateFunctionCode`・`GetFunction`・`GetFunctionConfiguration` だけ |

## マイグレーション

コードと db の形は揃えて出す必要がある。列を足す変更は **db を先に、コードを後に** 出す(古いコードは新しい列を知らないだけで動く)。
列を消す・名前を変える変更は、コードを先に消す側へ直してから db を変える。

AWS の db へは、作業する端末から踏み台越しに当てる(`tool.aws.rds` が `DEM_DATABASE_URL` を渡す。[aws-deploy.md](aws-deploy.md#手元から-db-へ繋ぐ))。

```
.venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c core/db/alembic/alembic.ini current
.venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c core/db/alembic/alembic.ini upgrade head
```

GitHub Actions からは当てない(db への道をワークフローに開けたくない・マイグレーションは中身を見てから当てたい)。
当て忘れは、web のセッションの `web_session.check_api` が版の食い違いとして報告する。

## 画面(Amplify)

- Amplify のアプリを `main` に繋ぐと、push のたびに `amplify.yml` で建て直す。建て直しの対象を `gui/web` の変更だけに
  絞るなら、Amplify の「ビルドの設定」でモノレポのアプリのパスを `gui/web` にしておく(`AMPLIFY_MONOREPO_APP_ROOT`)
- 型(`gui/web/lib/openapi.d.ts`)は API の OpenAPI から作ってコミットしてあるので、Amplify のビルドは python を要らない
- 画面と API の組み合わせがずれる(新しい画面が古い API を呼ぶ)ことがある。API を変えた PR は、Lambda の反映
  (数分)を待ってから画面が出るよう、API の変更を先に `main` へ入れるか、互換を保つ形にする
