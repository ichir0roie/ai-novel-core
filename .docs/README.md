# .docs — 設計と運用の覚え書き

人が読むための設計・運用の文書を置く。Claude 向けの作業指針は `CLAUDE.md` と `.claude/docs/` にある。

| 文書 | 中身 |
| --- | --- |
| [postgres.md](postgres.md) | PostgreSQL + PostGIS の db の作り方、`novel.db`(SQLite)からの移し方、二つの db の違い |
| [aws-deploy.md](aws-deploy.md) | AWS に置く形(Amplify の画面 / Lambda Web Adapter の API / RDS)、`infra/` の CDK、手元から db へ繋ぐ道(`tool.aws.rds`) |
| [ci-cd.md](ci-cd.md) | GitHub から Lambda・Amplify への自動デプロイ(OIDC・変数・マイグレーションの流し方) |
| [claude-tasks.md](claude-tasks.md) | Web にしたときの AI ボタンの扱い(`NOVEL_CLAUDE_MODE`)と、待ち行列・フラグを web のセッションが回す仕組み(`web_session/` と API の段) |
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
手元 ──(EC2 Instance Connect Endpoint)──▶ 踏み台 ┘ tool.aws.rds(マイグレーション・移し替え・確かめ)

Claude Code on the web のセッション: 頼まれたら web_session/run_ai_tasks が ai_task を拾い、claude -p で回す。
   db には直に繋がず、関数 URL の API の段(/api/steps)を通す(web-session.md)
```

AWS のリソースは `infra/` の CDK で持つ([aws-deploy.md](aws-deploy.md#infracdk))。Lambda と画面はこれから作る。

- ローカルは今までどおり SQLite の `novel.db` と `gui.dev` で動く。`DEM_DATABASE_URL` を渡したときだけ PostgreSQL を使う
- 開発では、手元(クラウドのセッションでも)に作った空の PostgreSQL + PostGIS を使う([postgres.md](postgres.md#開発用の-db))
- Lambda には claude が無いので、AI のボタンは「待ち行列に積む」だけにし、ユーザに頼まれた Claude Code on the web のセッションが後で回す
