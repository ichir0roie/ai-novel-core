# .docs — 設計と運用の覚え書き

人が読むための設計・運用の文書を置く。Claude 向けの作業指針は `CLAUDE.md` と `.claude/docs/` にある。

| 文書 | 中身 |
| --- | --- |
| [postgres.md](postgres.md) | PostgreSQL + PostGIS の db の作り方、`novel.db`(SQLite)からの移し方、二つの db の違い |
| [aws-deploy.md](aws-deploy.md) | AWS に置く形(Amplify の画面 / Lambda Web Adapter の API / Aurora・RDS)と組み立ての手順 |
| [ci-cd.md](ci-cd.md) | GitHub から Lambda・Amplify への自動デプロイ(OIDC・変数・マイグレーションの流し方) |
| [claude-tasks.md](claude-tasks.md) | Web にしたときの AI ボタンの扱い(`NOVEL_CLAUDE_MODE`)と、待ち行列・フラグをルーチンが拾う仕組み |
| [routine-db-connection.md](routine-db-connection.md) | Claude Code on the web のルーチンの環境から db に繋ぐ設定 |

## 全体の形

```
ブラウザ ──(Amplify のアクセス制御)──▶ Amplify Hosting: gui/web(Next.js)
                                          │ /api/* を route handler が流す(x-novel-api-key を付ける)
                                          ▼
                                   Lambda(関数 URL)+ Lambda Web Adapter: gui/api(FastAPI, uvicorn)
                                          │ SQLAlchemy(DEM_DATABASE_URL)
                                          ▼
                                   Aurora PostgreSQL(PostGIS)
                                          ▲
Claude Code のルーチン(クラウド) ────────┘ tool/routine/run_ai_tasks が ai_task を拾い、claude -p で回す
   ▲ API トリガー(/fire)で Lambda が起こす + 毎時のスケジュール
```

- ローカルは今までどおり SQLite の `novel.db` と `gui.dev` で動く。`DEM_DATABASE_URL` を渡したときだけ PostgreSQL を使う
- Lambda には claude が無いので、AI のボタンは「待ち行列に積む」だけにし、Claude Code のルーチンが後で回す
