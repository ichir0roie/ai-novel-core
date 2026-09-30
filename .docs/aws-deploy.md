# AWS に置く

画面(`gui/web`)を Amplify Hosting、API(`gui/api`)を Lambda + Lambda Web Adapter、db を Aurora PostgreSQL(PostGIS)に置く。
全体の図は [README.md](README.md)。

## 構成と決めたこと

| 部品 | 置き場所 | 決めたこと |
| --- | --- | --- |
| 画面 | Amplify Hosting(SSR) | モノレポの `gui/web` だけを建てる(`amplify.yml`)。ブラウザは同じオリジンの `/api/*` を叩き、Next.js の route handler(`gui/web/app/api/[...path]/route.ts`)がサーバー側で API へ流す |
| API | Lambda(コンテナ)+ 関数 URL | `deploy/lambda/Dockerfile`。Lambda Web Adapter が Lambda のイベントを HTTP に直すので、アプリは uvicorn で起こすだけ。コードに Lambda 専用の分岐を持たない |
| db | Aurora PostgreSQL(Serverless v2)+ PostGIS | [postgres.md](postgres.md)。Data API を有効にしておくと、HTTPS だけで繋げる(Lambda を VPC に入れなくてよい・ルーチンから繋げる。[routine-db-connection.md](routine-db-connection.md)) |
| AI | Claude Code のルーチン | Lambda には claude が無いので、AI のボタンは待ち行列に積むだけ(`NOVEL_CLAUDE_MODE=queue`)。[claude-tasks.md](claude-tasks.md) |

### 守り

公開の URL に置くので、二段で閉じる。

1. **画面**: Amplify の「アクセスコントロール」でブランチにユーザ名・パスワード(Basic 認証)を掛ける。
   CloudFront の段で掛かるので、`/api/*` の route handler も含めて全部が閉じる
2. **API**: `NOVEL_API_KEY` を Lambda と Amplify の両方に置く。API は `x-novel-api-key` が合わない要求を 401 で返す
   (`/api/ping` だけは Lambda Web Adapter の起動確認のため通す)。合言葉は Amplify のサーバー側でだけ足し、ブラウザには渡らない

より固くするなら、関数 URL の認証を `AWS_IAM` にし、Amplify の SSR の実行ロールから SigV4 で署名して呼ぶ(route handler を署名付きの fetch に替える)。
一人で使う間は上の二段で足りると判断した。

### Lambda を VPC に入れるか

| | A: VPC の外 + Data API(推奨) | B: VPC の中 + psycopg |
| --- | --- | --- |
| db への道 | `rds-data`(HTTPS)。ドライバは `sqlalchemy-aurora-data-api` | Aurora のエンドポイントへ TCP。ドライバは `psycopg`(同梱済み) |
| ルーチンを起こす(`api.anthropic.com` への `/fire`) | そのまま出られる | NAT ゲートウェイが要る(月 $30〜) |
| 速さ | 一文ごとに HTTPS。一覧・詳細の画面で数百 ms〜1 秒ほど遅くなる | 速い |
| 費用 | Data API の呼び出し分だけ | NAT の固定費 |
| 確かめたか | **未検証**(このリポジトリでは Data API のドライバを通していない) | ローカルの PostgreSQL + PostGIS で全 API を確かめた |

一人で使う画面なので A から始め、遅さが気になったら B に移す。どちらもコードは同じで、`DEM_DATABASE_URL` と
ドライバだけが替わる。A のときは Lambda のイメージに `sqlalchemy-aurora-data-api` を足し(`deploy/lambda/Dockerfile` の
`pip install` に並べる)、URL を `postgresql+auroradataapi://:@/novel` に、`AURORA_CLUSTER_ARN` / `AURORA_SECRET_ARN` を環境変数に置く。

## 組み立ての手順

リージョンは `ap-northeast-1` を例にする。

### 1. db

1. Aurora PostgreSQL(16 以上)の Serverless v2 クラスタを作る。最小 ACU は 0(自動の一時停止)で始めてよい
2. 「RDS Data API」を有効にする(A のとき)。マスターのパスワードは Secrets Manager に置く
3. 作業する端末から一度だけ繋げるようにし(一時的にパブリックアクセス + 自分の IP だけ、か踏み台)、
   [postgres.md](postgres.md) の `init_db` → `import_sqlite` を流す。終わったらパブリックアクセスを閉じる

### 2. API(Lambda)

1. ECR にリポジトリ(例 `novel-api`)を作る
2. イメージを建てて push する(以降は [ci-cd.md](ci-cd.md) の GitHub Actions が行う)

   ```
   docker build --platform linux/amd64 --provenance=false -f deploy/lambda/Dockerfile -t <ecr>/novel-api:init .
   docker push <ecr>/novel-api:init
   ```

3. そのイメージから Lambda 関数(例 `novel-api`)を作る。メモリ 1024 MB・タイムアウト 30 秒を目安にする
4. 関数 URL を作る(認証 `NONE`。守りは `NOVEL_API_KEY`)
5. 環境変数を置く

| 変数 | 値 |
| --- | --- |
| `DEM_DATABASE_URL` | db の URL(A: `postgresql+auroradataapi://:@/novel` / B: `postgresql+psycopg://…`) |
| `AURORA_CLUSTER_ARN` / `AURORA_SECRET_ARN` | A のときだけ |
| `NOVEL_API_KEY` | 長い乱数(`openssl rand -hex 32`) |
| `NOVEL_CLAUDE_MODE` | `queue`(イメージの既定。AI のボタンを消すなら `off`) |
| `NOVEL_ROUTINE_FIRE_URL` / `NOVEL_ROUTINE_FIRE_TOKEN` | ルーチンの API トリガーの URL と token([claude-tasks.md](claude-tasks.md))。無ければ毎時のスケジュールだけで拾う |

秘密(`NOVEL_API_KEY`・token・B のパスワード)は Lambda の環境変数を KMS で暗号化するか、Secrets Manager から読む形にする。

6. 実行ロールに、A なら `rds-data:ExecuteStatement` / `BatchExecuteStatement` / `BeginTransaction` / `CommitTransaction` /
   `RollbackTransaction`(そのクラスタ)と `secretsmanager:GetSecretValue`(その秘密)を付ける。B なら VPC の権限と、
   Aurora のセキュリティグループへの 5432 の許可

確かめ: `curl <関数 URL>/api/ping` が `{"ok":true}`、`curl -H 'x-novel-api-key: …' <関数 URL>/api/health` が `"dialect":"postgresql"`。

### 3. 画面(Amplify)

1. Amplify Hosting で「GitHub から」`ichir0roie/ai-novel-core` の `main` を繋ぐ。モノレポとして `gui/web` を指定する
   (ビルド設定はリポジトリの `amplify.yml` が使われる)
2. 環境変数

| 変数 | 値 |
| --- | --- |
| `AMPLIFY_MONOREPO_APP_ROOT` | `gui/web` |
| `NOVEL_API_URL` | Lambda の関数 URL(末尾の `/` は無くてよい) |
| `NOVEL_API_KEY` | Lambda と同じ値 |

`amplify.yml` がビルドのときに `NOVEL_*` を `.env.production` に写す(SSR のサーバーは実行時にコンソールの環境変数を
読めないため。Amplify の案内どおりの形)。
3. 「アクセスコントロール」で `main` ブランチにユーザ名・パスワードを掛ける
4. 以降は `main` への push で Amplify が建て直す

Next.js は 16 系を使っている。Amplify の SSR が対応する版は Amplify のドキュメントで確かめる(ビルドが通っても、
実行で落ちるときは版の対応を疑う)。`next build` はこのリポジトリで通ることを確かめてある。

## ローカルとの違い

| | ローカル(`gui.dev`) | AWS |
| --- | --- | --- |
| db | SQLite の `novel.db` | Aurora PostgreSQL |
| `/api/*` の流し先 | `NOVEL_API_URL` 既定 `http://127.0.0.1:8765` | Lambda の関数 URL |
| 合言葉 | 無し(`NOVEL_API_KEY` 空) | 有り |
| AI のボタン | その場で回す(`direct`) | 待ち行列に積む(`queue`) |
| 裏の job | プロセスのメモリ | `ai_task` の行(Lambda は応答のあとに走り続けられないので、`background` の呼び出しも行に積む) |
