# AWS に置く

画面(`gui/web`)を Amplify Hosting、API(`gui/api`)を Lambda + Lambda Web Adapter、db を RDS for PostgreSQL(PostGIS)に置く。
リソースは `infra/` の CDK(TypeScript)で持つ。費用を抑えるため、アカウントに既にあるリソースは作り直さずに参照する。
全体の図は [README.md](README.md)。

## 構成と決めたこと

| 部品 | 置き場所 | 決めたこと |
| --- | --- | --- |
| 画面 | Amplify Hosting(SSR) | モノレポの `gui/web` だけを建てる(`amplify.yml`)。ブラウザは同じオリジンの `/api/*` を叩き、Next.js の route handler(`gui/web/app/api/[...path]/route.ts`)がサーバー側で API へ流す |
| API | Lambda(コンテナ)+ 関数 URL | `infra/lambda/Dockerfile`。Lambda Web Adapter が Lambda のイベントを HTTP に直すので、アプリは uvicorn で起こすだけ。コードに Lambda 専用の分岐を持たない |
| db | RDS for PostgreSQL(16 以上。db.t4g.micro 程度)+ PostGIS | private subnet に置き、公開しない。手元からは踏み台越しにだけ繋ぐ(下の「手元から db へ繋ぐ」)。Aurora ではないので Data API は無い |
| AI | Claude Code on the web のセッション | Lambda には claude が無いので、AI のボタンは待ち行列に積むだけ(`NOVEL_CLAUDE_MODE=queue`)。頼まれたセッションが `claude -p` を回し、db には API の段(`/api/steps`)越しに触る。[claude-tasks.md](claude-tasks.md) |
| リソースの管理 | `infra/`(AWS CDK) | コンソールで手で作らない。構築ごとの設定は core に書かず、SSM の `/novel/deploy/config` に置く(下の「構築ごとの設定」) |

### 構築ごとの設定

core は公開リポジトリで、誰がクローンしても自分の AWS アカウントに建てられる形にしてある。そのため、アカウント ID やリソースの ID は
core のどこにも書かない。

- アカウントとリージョンは、`cdk` を動かす人の AWS CLI のプロファイルから取る
- 構築ごとの設定は、構築するアカウントの SSM パラメータ `/novel/deploy/config` に JSON で置く(標準のパラメータなので料金は掛からない)。
  すでにあるリソースを使い回すならその ID を、GitHub Actions からデプロイするなら自分の core(上流か、自分のフォーク)のリポジトリを書く。
  どのリポジトリにも置かないので、公開のフォークからでも値は漏れない
- `infra/` は synth のときにこれを読む(無ければ止まる)。形の見本は `infra/aws.example.json`。埋めたものを置くには:
  `aws ssm put-parameter --name /novel/deploy/config --type String --value file://aws.json`(直すときは `--overwrite` を足す)

  ```json
  {
    "github": { "repository": "<owner>/<repo>", "branch": "main" },
    "existing": {
      "vpcId": "vpc-…",
      "dbInstanceIdentifier": "<RDS のインスタンス名>",
      "bastion": { "instanceId": "i-…", "instanceConnectEndpointId": "eice-…" },
      "functionSubnetIds": ["subnet-…", "subnet-…"]
    }
  }
  ```

  | 項目 | 中身 |
  | --- | --- |
  | `github` | 必須。CI のロールを引き受けられる、自分の core のリポジトリとブランチ |
  | `github.subClaimPrefix` | 任意。GitHub の OIDC の sub の前半。リポジトリが immutable subject(sub が `repo:<owner>@<ID>/<repo>@<ID>` の形)なら要る。`gh api repos/<owner>/<repo>/actions/oidc/customization/sub` の `sub_claim_prefix` をそのまま置く。無ければ `repo:<repository>` |
  | `existing` | 全部任意。無いものはスタックが作る |
  | `existing.vpcId` | 無く、`dbInstanceIdentifier` があれば、その db の VPC を使う |
  | `existing.dbInstanceIdentifier` | 使い回す RDS。マスターのパスワードは RDS の管理(`--manage-master-user-password`)にしておく。エンドポイント・セキュリティグループ・秘密の ARN は、synth のときにこの名前から引くので、設定に書かない |
  | `existing.functionSubnetIds` | Lambda を置く subnet。無ければ VPC の isolated subnet を全部使う |

- 使い回すリソースの ID が無ければ、`infra/` のスタック(`NovelData`)が次を作る。作った値も SSM の `/novel/*` に置く
- deploy のあとに決まる値(関数 URL など)は SSM の `/novel/*` に置き、手元の道具や web の環境の設定はそこから引く
- CDK が手元に貯める `infra/cdk.context.json` は、アカウントやリソースの ID を含むので git に入れない

| リソース | 役目 |
| --- | --- |
| VPC | 2 AZ の isolated subnet だけ。NAT ゲートウェイもインターネットゲートウェイも置かないので、外(インターネット)へは出られない |
| RDS for PostgreSQL(db.t4g.micro・20 GB) | db `novel`。IAM データベース認証・バックアップ 7 日・削除保護を有効にし、消すときはスナップショットを残す。セキュリティグループは、踏み台と Lambda のセキュリティグループからの 5432 だけを通す。マスターのパスワードは RDS が管理する Secrets Manager の秘密に置き、RDS が 7 日ごとに回す |
| EC2 の踏み台(t4g.nano・公開 IP 無し) | ふだんは止めておき、使うときだけ起こす |
| EC2 Instance Connect Endpoint | 公開 IP の無い踏み台へ、AWS の API 越しに SSH を通す(料金は掛からない) |

## infra(CDK)

`infra` で動かす。bootstrap(`CDKToolkit`)は済んでいる。

```
cd infra
npm install
npx cdk diff      # 変わるものを見る
npx cdk deploy    # 当てる
```

| スタック | 中身 |
| --- | --- |
| `NovelData` | 手元の道具とほかのスタックが引く値を、SSM パラメータ `/novel/*` に置く(db のエンドポイント・ポート・db 名・マスターの秘密の ARN、踏み台と EC2 Instance Connect Endpoint の ID)。標準のパラメータなので料金は掛からない |
| `NovelCi` | ECR リポジトリ `novel-api`、GitHub の OIDC プロバイダ、CI のロール `github-ai-novel-core-deploy`([ci-cd.md](ci-cd.md)) |
| `NovelApi` | Lambda `novel-api`(VPC の中)・関数 URL・セキュリティグループ・実行ロール・ログの出し先(保存 2 週間。CloudWatch Logs の無料枠に収める)。関数 URL は SSM の `/novel/api/function-url` にも出す |
| `NovelAuth` | 画面のログインに使う Cognito のユーザープール(料金区分 Lite。月 1 万人まで無料)と、画面用のアプリクライアント。ID は SSM の `/novel/auth/user-pool-id`・`/novel/auth/user-pool-client-id` に出す |

## 手元から db へ繋ぐ

```
手元 ──ssh(EC2 Instance Connect Endpoint の open-tunnel)──▶ 踏み台 ──5432──▶ RDS
```

`tool.aws.rds` が、踏み台を起こすところから転送を張るところまでを行う。使い方は二つ。リポジトリのルートで:

```
.venv/bin/python -m tool.aws.rds --serve   # ふだん用。127.0.0.1:15432 に転送を張り続ける
.venv/bin/python -m tool.aws.rds -- .venv/bin/python -m alembic -c db/alembic/alembic.ini upgrade head   # マスターで流す
.venv/bin/python -m tool.aws.rds --database postgres -- psql
.venv/bin/python -m tool.aws.rds          # マスターで繋いだまま $SHELL を開く。exit で閉じる
```

| 使い方 | 繋ぐ db のロール | 認証 |
| --- | --- | --- |
| `--serve`(ふだんの読み書き。SessionStart フックと VS Code のタスク「db tunnel」が起こす) | `novel_app`(行の読み書きだけ) | IAM データベース認証。`DEM_DATABASE_URL=postgresql+psycopg://novel_app@127.0.0.1:15432/novel?sslmode=require` と `DEM_DATABASE_IAM_AUTH=1` を渡した python が、繋ぐたびにトークンを作る。トークンは RDS の本来のエンドポイント(SSM の `/novel/db/endpoint`)に宛てて作る |
| `-- <コマンド>`(マイグレーション・表の権限を変える SQL など、DDL が要る作業) | マスター | RDS が管理する秘密からパスワードを読み、`DEM_DATABASE_URL`・`PG*` にして渡す。既定のポートは 15433 |

1. SSM の `/novel/*` から db と踏み台を引く
2. 踏み台が止まっていれば起こす
3. 使い捨ての鍵を EC2 Instance Connect で踏み台に送り(60 秒だけ効く)、ssh で db のポートを手元の `--port` へ転送する
4. `--serve` は転送が切れるたびに張り直す(EC2 Instance Connect Endpoint の転送は一本 1 時間で切れる)。コマンドを渡したときは、
   マスターの秘密からパスワードを読んでコマンドを流す
5. 自分で起こした踏み台は、終わるときに止める(`--serve` は Ctrl+C か SIGTERM で終わる)

- 要るもの: AWS CLI v2、ssh、AWS の権限(`ssm:GetParametersByPath`・`ssm:GetParameters`・`ec2:DescribeInstances`・`ec2:StartInstances`・`ec2:StopInstances`・
  `ec2-instance-connect:SendSSHPublicKey`・`ec2-instance-connect:OpenTunnel`・`rds-db:connect`(`novel_app`)・`secretsmanager:GetSecretValue`(マスター))
- パスワードは手でどこかに写さない。ふだんの接続はパスワードを持たず、マスターのパスワードは RDS が回すので毎回秘密から読み直す
- `--serve` を動かしている間は踏み台も動き続ける(t4g.nano)。使わない間は止める(`pkill -f 'tool.aws.rds --serve'`)
- `--serve` とコマンドを渡す方は別のポートで聞くので、同時に動かせる。ただし、先に踏み台を起こした方が終わるときに踏み台を止め、
  もう一方の転送も切れる。コマンドを渡す方を `--serve` の最中に回すなら、踏み台は `--serve` が起こしたものなので止まらない

## API(Lambda)

`infra/` のスタックで作る(ECR・関数・関数 URL・実行ロール・セキュリティグループ)。

### RDS(Aurora でない)から来る決まり

- Data API が無いので、Lambda を VPC の中に置き、psycopg で db に繋ぐ。db のセキュリティグループに、Lambda のセキュリティグループからの 5432 を足す
- private subnet から外へ出るには NAT ゲートウェイ(東京で月 $45 ほど)が要る。費用を抑えるため置かない。そのため:
  - db のパスワードは Secrets Manager から読めない(読むにはインターフェースエンドポイントが要り、月 $10 ほど掛かる)。
    IAM データベース認証を使う(接続の token は Lambda の中で署名して作るので、外へ出なくてよい)
  - Lambda から外(`api.anthropic.com` など)も叩けない。AI の依頼は待ち行列に積むだけにし、web のセッションに頼んで回す([claude-tasks.md](claude-tasks.md))

### 手順の骨組み

1. API の合言葉を SSM の SecureString に作る(`/novel/api-keys/gui`・`/novel/api-keys/web`)。`infra/` のスタックは synth のときにこれを読むので、
   無いうちはどのスタックの synth も `ParameterNotFound` で止まる。一番初めに作る

   ```
   aws ssm put-parameter --name /novel/api-keys/gui --type SecureString --value "$(openssl rand -hex 32)"
   aws ssm put-parameter --name /novel/api-keys/web --type SecureString --value "$(openssl rand -hex 32)"
   ```

2. `npx cdk deploy NovelCi`(ECR リポジトリ `novel-api` と CI のロール。[ci-cd.md](ci-cd.md#aws-側の用意一度だけ))
3. 最初のイメージを手元で建て、`main` の tag で push する(`infra/lambda/push-image.sh`)。以降は GitHub Actions が `<sha>` と `main` で push する
4. `npx cdk deploy NovelApi` で関数(メモリ 1024 MB・タイムアウト 30 秒・private subnet は二つの AZ のもの)と関数 URL(認証 `NONE`)を deploy する。
   関数は `novel-api:main` のイメージで作り、CDK は自分でイメージを建てない(CI との分担は [ci-cd.md](ci-cd.md#cdk-との分担))
5. 環境変数は CDK が置く

| 変数 | 値 |
| --- | --- |
| `DEM_DATABASE_URL` | `postgresql+psycopg://novel_app@<RDS のエンドポイント>:5432/novel?sslmode=require`(パスワードは書かない) |
| `DEM_DATABASE_IAM_AUTH` | `1`。接続を張るたびに IAM データベース認証の token を作り、パスワードの代わりに渡す |
| `NOVEL_API_KEYS` | 呼ぶ側ごとの合言葉(`gui=<鍵>,web=<鍵>`)。それぞれ長い乱数(`openssl rand -hex 32`)。どの鍵で来たかをログに出す |
| `NOVEL_CLAUDE_MODE` | `queue`(イメージの既定。AI のボタンを消すなら `off`) |

確かめ: `curl <関数 URL>/api/ping` が `{"ok":true}`、`curl -H 'x-novel-api-key: …' <関数 URL>/api/health` が `"dialect":"postgresql"`。

db のロール `novel_app`(行の読み書きだけ。IAM データベース認証で繋ぐ)は、マスターで `infra/sql/novel_app.sql` を流して作る。

## 画面(Amplify)(これから作る)

1. Amplify Hosting で、自分の core のリポジトリ(フォーク)の `main` を繋ぐ。モノレポとして `gui/web` を指定する
   (ビルド設定はリポジトリのルートの `amplify.yml` が使われる)
2. 環境変数

| 変数 | 値 |
| --- | --- |
| `AMPLIFY_MONOREPO_APP_ROOT` | `gui/web` |
| `NOVEL_API_URL` | Lambda の関数 URL(末尾の `/` は無くてよい) |
| `NOVEL_API_KEY` | Lambda の `NOVEL_API_KEYS` の `gui=` と同じ値 |
| `NOVEL_WEB_API_KEY` | Lambda の `NOVEL_API_KEYS` の `web=` と同じ値。web のセッションの `/api/*` を、Amplify の段でも確かめるのに使う |
| `NEXT_PUBLIC_NOVEL_USER_POOL_ID` | SSM の `/novel/auth/user-pool-id`(`npx cdk deploy NovelAuth` のあと) |
| `NEXT_PUBLIC_NOVEL_USER_POOL_CLIENT_ID` | SSM の `/novel/auth/user-pool-client-id` |

`amplify.yml` がビルドのときに `NOVEL_*` を `.env.production` に写す(SSR のサーバーは実行時にコンソールの環境変数を
読めないため。Amplify の案内どおりの形)。`NEXT_PUBLIC_*` は秘密ではなく、`next build` がブラウザ向けのコードにも埋め込む。
`AMPLIFY_APP_ORIGIN` は置かない(置くと adapter-nextjs がサーバー側でログインする形に切り替わり、画面の Authenticator が使えなくなる)。
3. 画面に入る人を Cognito に作る(画面からの登録は閉じてある)。仮のパスワードがメールで届き、最初のログインで替える:
   `aws cognito-idp admin-create-user --user-pool-id <ユーザープールの ID> --username <メールアドレス> --user-attributes Name=email,Value=<メールアドレス> Name=email_verified,Value=true`
4. 以降は `main` への push で Amplify が建て直す

Next.js は 16 系を使っている。Amplify の SSR が対応する版は Amplify のドキュメントで確かめる(ビルドが通っても、
実行で落ちるときは版の対応を疑う)。`next build` はこのリポジトリで通ることを確かめてある。

## 守り

公開の URL に置くので、二段で閉じる。

1. 画面: Amplify の Auth で Cognito(`NovelAuth`)にログインする(`gui/web/components/AuthGate.tsx`)。ログインするまで画面の中身は出さない。
   トークンはクッキーに置き、`/api/*` の route handler が、adapter-nextjs で Cognito の公開鍵による署名を確かめてから流す。
   更新のトークンは 365 日効くので、その間はログインし直さなくてよい。
   web のセッションは Cognito に入らず、`x-novel-api-key` に web 用の合言葉を付けて `/api/*` を叩く。Amplify が
   `NOVEL_WEB_API_KEY` と合うかを見てから流し、Lambda がもう一度見る。
   Amplify の「アクセスコントロール」(Basic 認証)は、ブラウザを閉じるたびに入れ直しになるので使わない
2. API: 合言葉を呼ぶ側ごとに分ける(Amplify 用の `gui`、Claude Code on the web 用の `web`)。Lambda の `NOVEL_API_KEYS` に両方を置き、
   API は `x-novel-api-key` がどれにも合わない要求を 401 で返す(`/api/ping` だけは Lambda Web Adapter の起動確認のため通す)。
   片方が漏れたら、それだけを替えるか外す。Amplify の合言葉はサーバー側でだけ足し、ブラウザには渡らない

合言葉の元は SSM の SecureString(`/novel/api-keys/gui`・`/novel/api-keys/web`)に置き、`cdk deploy` のときに Lambda の環境変数へ入れる。
VPC の中の Lambda は SSM に届かない(届くにはインターフェースエンドポイントの費用が掛かる)ので、起動のたびに読む形にはしない。
その代わり、値は CloudFormation の template と手元の `cdk.out/`(git からは外してある)にも載る。
Lambda の環境変数を読める人にはどのみち見えるので、一人で使う間はこれでよいとした。値をログや報告に出さない

合言葉を替える(`<gui|web>` は替える側):

1. `aws ssm put-parameter --name /novel/api-keys/<gui|web> --type SecureString --overwrite --value "$(openssl rand -hex 32)"`
2. `infra` で `npx cdk deploy NovelApi`。Lambda の環境変数が替わり、古い鍵はその時点で通らなくなる
3. `gui` を替えたら Amplify の `NOVEL_API_KEY` を替えて建て直す。`web` を替えたら Amplify の `NOVEL_WEB_API_KEY` を替えて建て直し、
   web の環境の `NOVEL_API_KEY` も替える

2 と 3 の間は、替えた側の呼び出しが 401 になる。止めずに替えたくなったら、同じ呼ぶ側に新旧二つの鍵を一時的に置ける形を
`NOVEL_API_KEYS` に足す。

より固くするなら、関数 URL の認証を `AWS_IAM` にし、Amplify の SSR の実行ロールから SigV4 で署名して呼ぶ(route handler を署名付きの fetch に替える)。
一人で使う間は上の二段で足りると判断した。

db は公開しない。db のセキュリティグループが通すのは、踏み台(と、作ったあとの Lambda)のセキュリティグループからだけにする。

db の側でも絞る。Lambda が使うロール `novel_app` には行の読み書き(DML)だけを許し、表を作る・変える権限(DDL)は与えない。
API に任意の SQL を受ける口は作らず、公開するのは `data_access_logic` の入口と画面のための決まった操作だけにする。
こうしておけば、合言葉が漏れても、web の Claude が誤った指示に従っても、できることは入口の範囲の行の操作に収まる。
その外側の備えとして、RDS の自動バックアップを 7 日保ち(その間の任意の時点へ戻せる)、削除保護を掛ける。

## ローカルとの違い

| | ローカル(`gui.dev`) | AWS |
| --- | --- | --- |
| db | 同じ RDS(踏み台越しの転送、`novel_app` の IAM 認証) | RDS for PostgreSQL(db `novel`。VPC の中から、`novel_app` の IAM 認証) |
| `/api/*` の流し先 | `NOVEL_API_URL` 既定 `http://127.0.0.1:8765` | Lambda の関数 URL |
| 合言葉 | 無し(`NOVEL_API_KEY` 空) | 有り |
| AI のボタン | その場で回す(`direct`) | 待ち行列に積む(`queue`) |
| 裏の job | プロセスのメモリ | `ai_task` の行(Lambda は応答のあとに走り続けられないので、`background` の呼び出しも行に積む) |
