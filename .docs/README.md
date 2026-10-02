# .docs — 設計と運用の覚え書き

人が読むための設計・運用の文書を置く。Claude 向けの作業指針は `CLAUDE.md` と `.claude/docs/` にある。

| 文書 | 中身 |
| --- | --- |
| [postgres.md](postgres.md) | PostgreSQL + PostGIS の db の作り方、開発・テスト用の手元の db、db から db への写し方、SQLite との違い |
| [aws-deploy.md](aws-deploy.md) | AWS に置く形(Amplify の画面 / Lambda Web Adapter の API / RDS)、`infra/` の CDK、手元から db へ繋ぐ道(`tool.aws.rds`) |
| [ci-cd.md](ci-cd.md) | GitHub から Lambda・Amplify への自動デプロイ(OIDC・変数・マイグレーションの流し方) |
| [claude-tasks.md](claude-tasks.md) | AI(claude)を web のセッションが回す仕組み(`web_session/` と API の段)と、後回しの AI の段 |
| [cost.md](cost.md) | 費用の見直し(RDS を EC2 と S3 のバックアップに替える案・リザーブドインスタンス、main へのマージごとのデプロイの費用) |
| [web-session.md](web-session.md) | Claude Code on the web のセッションから db に届く道(API を通す。その環境の設定) |

## 全体の形

```
ブラウザ ──(Amplify のアクセス制御)──▶ Amplify Hosting: gui/web(Next.js)
                                          │ /api/* を route handler が流す(x-novel-api-key を付ける)
                                          ▼
                                   Lambda(関数 URL)+ Lambda Web Adapter: gui/api(FastAPI, uvicorn)
                                          │ SQLAlchemy(DEM_DATABASE_URL)。VPC の中
                                          ▼
                                   RDS for PostgreSQL(PostGIS。private subnet)
                                          ▲
手元 ──(EC2 Instance Connect Endpoint)──▶ 踏み台 ┘ tool.aws.rds(--serve: ふだんの読み書き。-- <コマンド>: マイグレーションなど)

Claude Code on the web のセッション: web_session/ の流れで claude -p を回す。
   db には直に繋がず、関数 URL の API の段(/api/steps)を通す(web-session.md)
```

AWS のリソースは `infra/` の CDK で持つ([aws-deploy.md](aws-deploy.md#infracdk))。

- db は RDS ただ一つ。手元の CLI・`gui.dev`・Claude Code も、踏み台越しの転送(`tool.aws.rds --serve`)で RDS を読み書きする(`.claude/docs/setup.md`)。以前の SQLite の `novel.db` は使わない
- 開発では、手元(クラウドのセッションでも)に作った空の PostgreSQL + PostGIS を使う([postgres.md](postgres.md#開発用の-db))
- Lambda には claude が無い。画面には AI のボタンを置かず、AI は Claude のセッション(手元か Claude Code on the web)が回す
