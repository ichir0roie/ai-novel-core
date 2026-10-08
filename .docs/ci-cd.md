# 自動デプロイ(GitHub → Lambda / Amplify)

| 何を | きっかけ | 仕組み |
| --- | --- | --- |
| API(Lambda) | `main` への push のうち、API が読むコード(`ai/` `data_access_logic/` `db/` `randomizer/` `gui/api/` `requirements.txt` `infra/lambda/`)が変わったとき。手で回すなら Actions の「Run workflow」 | `.github/workflows/deploy-api.yml` |
| 画面(Amplify) | `main` への push | Amplify が GitHub を見て `amplify.yml` で建てる(GitHub Actions は使わない) |
| db のマイグレーション | API と同じ。API を差し替える前に流す | `.github/workflows/deploy-api.yml` → Lambda `novel-migrate`(下の「マイグレーション」) |

## API の流れ

1. `ruff check`(実行時の誤りだけを見る設定。`ruff.toml`)
2. OIDC で AWS のロールを引き受ける(鍵を GitHub に置かない)
3. `infra/lambda/Dockerfile` を `linux/arm64` で建て、ECR に `<commit の sha>` と `main` の二つの tag で push
   (`--provenance=false`。Lambda は複数アーキの目録を受け付けない)。依存は建てる側のアーキで arm64 の wheel を落として入れ、
   arm64 の段では RUN を回さないので、x86 のランナーのまま QEMU 無しで建つ
4. 変数 `MIGRATION_FUNCTION_NAME` があれば、マイグレーションの関数を同じイメージに差し替えて呼び、db を新しいバージョンにする(下の「マイグレーション」)。
   失敗したら API は差し替えない
5. `aws lambda update-function-code`(`<commit の sha>` の tag。関数のアーキ `arm64` も一緒に渡す)→ 反映を待つ
6. 秘密の `API_BASE_URL` があれば `/api/ping` を叩いて確かめる

変数 `LAMBDA_FUNCTION_NAME` が無ければ、ジョブは飛ばされる(このリポジトリは公開なので、フォークや設定前に落ちないようにしている)。
公開リポジトリの Actions のログは誰でも読め、変数(Variables)はログに伏せ字にならない。
アカウント ID を含むロールの ARN と関数 URL は秘密(Secrets)に置く(ログでは `***` になる)。アカウント ID も `mask-aws-account-id` で伏せる。

Settings → Secrets and variables → Actions の **Variables**:

| 変数 | 例 |
| --- | --- |
| `AWS_REGION` | `ap-northeast-1` |
| `ECR_REPOSITORY` | `novel-api` |
| `LAMBDA_FUNCTION_NAME` | `novel-api` |
| `MIGRATION_FUNCTION_NAME` | `novel-migrate`(`NovelApi` で関数を作ってから置く。無ければマイグレーションを飛ばす) |

同じ画面の **Secrets**:

| 秘密 | 例 |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/github-ai-novel-core-deploy` |
| `API_BASE_URL` | Lambda の関数 URL(任意。煙の確かめ用。末尾の `/` は除く) |

## CDK との分担

関数は `infra/` の CDK(`NovelApi`)で持つが、関数のコード(イメージ)だけは CI が差し替える。

| 持ち主 | 持つもの |
| --- | --- |
| CDK(手元から `cdk deploy`) | ECR リポジトリ `novel-api`(ライフサイクルで新しい 30 個を残す)、関数の設定(環境変数・VPC・実行ロール・関数 URL)、GitHub Actions の OIDC のロール |
| CI(`deploy-api.yml`) | イメージを建てて push し、関数(`novel-api`・`novel-migrate`)のコードを差し替える。`novel-migrate` を呼んでマイグレーションを流す |

- CDK は関数を `novel-api:main` のイメージで作り、自分ではイメージを建てない。`cdk deploy` は template の `ImageUri` が変わらない限りコードに触れないので、
  CI が差し替えたイメージは、そのあとの `cdk deploy` でも戻らない。関数を作り直すことになっても、その時点の `main` の tag(一番新しいイメージ)を使う
- CI からは `cdk deploy` を流さない。このリポジトリは公開なので、CI の権限を ECR への push とその関数のコードの差し替えだけに絞る。
  `cdk deploy` を CI に許すと、CDK の bootstrap の実行ロール(既定で管理者の権限)を通してアカウントを何でも変えられるようになり、
  synth のときに読む API の合言葉(SSM の SecureString)も CI に渡すことになる
- 最初の一回は、関数を作る前に手元で建てて `main` の tag で push する(関数が無いと、CI の `update-function-code` が落ちる)。
  順番は、ECR を deploy → 手元で push → 関数を deploy

## AWS 側の用意(一度だけ)

ECR・OIDC・CI のロールは手で作らず、`infra/` の `NovelCi` スタック(`infra/lib/ci-stack.ts`)で作る。

1. `infra` で `npx cdk deploy NovelCi`
2. 出力の `DeployRoleArn` を、リポジトリの秘密 `AWS_DEPLOY_ROLE_ARN` に置く

`NovelCi` が作るもの:

| リソース | 中身 |
| --- | --- |
| ECR リポジトリ `novel-api` | tag の無いイメージは push から 1 日で消し、残りは新しい 30 個を残す。スタックを消してもリポジトリは残す |
| GitHub の OIDC プロバイダ | `token.actions.githubusercontent.com`、対象 `sts.amazonaws.com` |
| CI のロール | 信頼は、SSM の `/novel/deploy/config` に書いた自分の core のリポジトリの `main` だけ(`repo:<owner>/<repo>:ref:refs/heads/main`。immutable subject のリポジトリは `github.subClaimPrefix` の値が前半に入る。公開リポジトリなので、PR やフォークから引き受けられないようにする)。権限は `novel-api` の ECR への push と読み取り(buildx の push と関数の差し替えがイメージを読む)と、関数 `novel-api`・`novel-migrate` の `UpdateFunctionCode`・`GetFunction`・`GetFunctionConfiguration`、`novel-migrate` の `InvokeFunction`、`novel-api` の関数 URL の呼び出しだけ。db への道は持たない |

## マイグレーション

`main` へのマージで API を出すたびに、CI が db を新しいバージョンにしてから API を差し替える(**db を先に、コードを後に**)。
列を足す変更は、新しい API がまだ無い列を読まないので安全。列を消す・名前を変える変更は、マイグレーションのあと API を差し替えるまでの
1〜2 分だけ、古い API が消えた列を読んで失敗しうる(一人で使う道具なので許している)。

| 何が | どう |
| --- | --- |
| Lambda `novel-migrate` | API と同じイメージを、コマンドだけ `db/migration_app.py` に差し替えて動かす。Lambda Web Adapter が `aws lambda invoke` を `POST /events` に流し、`alembic upgrade head` を流して `{"before", "after", "head"}` を返す。呼び出しの中身は見ないので、イメージに入っているバージョンまで当てる以外のことはできない。同時に一つしか動かない(予約の同時実行 1)。タイムアウト 15 分 |
| db のロール `novel_migrator` | 表の持ち主。IAM データベース認証で繋ぐ(パスワードを持たない)。`novel_migrator` が作った表・連番には、既定の権限で `novel_app` の行の読み書きが付く(`infra/sql/novel_migrator.sql`) |
| CI(`deploy-api.yml` の `migrate db`) | `novel-migrate` を新しいイメージに差し替えて呼び、`after` が `head` と同じでなければ止まる(API は差し替えない)。返事は 16 分まで待つ(TCP の keepalive で無通信の接続が切られないようにしている)。ログは CloudWatch Logs の `novel-migrate` のロググループ |

- GitHub Actions には db への道も、マスターの秘密も渡さない。CI ができるのは、`main` のイメージを `novel-migrate` に入れて呼ぶことだけ
- マイグレーションの中身は、PR のレビューで見てからマージする
- 手元から当てるとき(CI を待たずに当てる・downgrade する)は、転送(`tool.aws.rds --serve`)越しに `novel_migrator` へ IAM 認証で入って流す。
  手元の AWS CLI の権限に、`novel_migrator` への `rds-db:connect` が要る
- マスターは `novel_migrator` の一員にしない。RDS は `rds_iam` を持つロールの一員を(継承を外しても)IAM 認証だけに絞るので、
  マスターがパスワードで入れなくなる。`novel_migrator.sql` は、持ち主を移す間だけマスターを一員にし、同じトランザクションの終わりに外す

```
.venv/bin/python -m alembic -c db/alembic/alembic.ini current   # バージョンを見るだけなら、ふだんの接続でよい
DEM_DATABASE_URL='postgresql+psycopg://novel_migrator@127.0.0.1:15432/novel?sslmode=require' .venv/bin/python -m alembic -c db/alembic/alembic.ini upgrade head   # 手で当てる
```

当て忘れ・失敗は、web のセッションの `web_session.check_api` がバージョンの食い違いとして報告する。

### 最初の一回

1. `NovelCi` と `NovelApi` を `cdk deploy` する(`novel-migrate` と、CI のロールの権限が増える)
2. マスターで `infra/sql/novel_migrator.sql` を流す(ロールを作り、マスターが持っていた表の持ち主を移す)

   ```
   .venv/bin/python -m tool.aws.rds -- psql -1 -v ON_ERROR_STOP=1 -f infra/sql/novel_migrator.sql
   ```

3. リポジトリの変数 `MIGRATION_FUNCTION_NAME` に `novel-migrate` を置く。以降の `main` へのマージから CI が当てる。
   すぐに当てるなら、Actions の「Run workflow」で deploy-api を回す

## 画面(Amplify)

- Amplify のアプリを `main` に繋ぐと、push のたびに `amplify.yml` で建て直す。建て直しの対象を `gui/web` の変更だけに
  絞るなら、Amplify の「ビルドの設定」でモノレポのアプリのパスを `gui/web` にしておく(`AMPLIFY_MONOREPO_APP_ROOT`)
- 型(`gui/web/lib/openapi.d.ts`)は API の OpenAPI から作ってコミットしてあるので、Amplify のビルドは python を要らない
- 画面と API の組み合わせがずれる(新しい画面が古い API を呼ぶ)ことがある。API を変えた PR は、Lambda の反映
  (数分)を待ってから画面が出るよう、API の変更を先に `main` へ入れるか、互換を保つ形にする
