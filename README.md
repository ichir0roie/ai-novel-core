# ai-novel-core

AI にラノベを書いてもらうためのプロジェクト。
これで生成されるデータ(世界の記録と本文)は、自分の AWS に建てた db(RDS for PostgreSQL)に置き、このリポジトリには入れない。
建て方は `.docs/aws-deploy.md`、手元の用意は `.claude/docs/setup.md`。

## 特徴

- **世界が先、本文が後。** 場所・人物・人物相関・出来事・アイデアをすべて db に記録し、
  本文(`episode`)はその時点・その場所の断面を引いてから書く
- **AI が世界を組み立てる。** 作者の下書きを核に、人物・出来事・話を Claude Code(`claude -p`)に生成させて db に積む
- **db に触れる処理を一本化。** db を読み書きする処理と入口は `data_access_logic/` にまとめ、Claude(CLI)も GUI の API も同じ入口を呼ぶ。
  下書きを「作る」側は db に触れず下書きのモデルを返し、「確定する」側が実在確認とスキーマの検証をして書き込む
- **GUI で読める・直せる。** `gui/`(FastAPI + Next.js)で一覧・修正・追加と、
  星ごとの地図(svg / html)と人物相関図を見る
- **本文はプロットから書く。** 話ごとに作者がプロット(`plot_text`。場面割りと狙い)を置き、AI か作者が本文(`main_text`)を書く
- **時間に上限がない。** 年は何桁でもよく(ノウル一万年代など)、遠未来の世界線も同じ仕組みで扱う
- **テストは本番に触れない。** 本番を手元の PostGIS に写したテスト用の db とモック AI で、AI 無しに生成を回せる



## ディレクトリ

| ディレクトリ     | 役割                                                          |
| ---------------- | ------------------------------------------------------------- |
| `db/` `ai/` ほか | 仕組み。db の形・入口・問い合わせ・AI の client               |
| db(RDS)        | **世界の記録と本文そのもの**(PostgreSQL + PostGIS。AWS 側)    |
| `gui/`           | データ編集 GUI(API と画面)。使い方は `gui/readme.md`         |
| `.docs/`         | 設計・運用の文書(PostgreSQL・AWS へのデプロイ・web の AI)      |
| `CLAUDE.md`      | **Claude 向けの作業指針**                                     |

```
db/                 **記録の形(SQLAlchemy)。列はここ一か所で決まる**
                    alembic/ にマイグレーション、postgres/ に PostgreSQL(PostGIS)の作成・db から db への写し
data_access_logic/  **db を読み書きする処理と入口。db に触れるのはここ越しだけ**(一覧は data_access_logic/readme.md)
                    location/ character/ event/ event_seed/ story/ episode/ idea/ meme/ oracle/ review/ fact_check/ map/ query/
                    <領域>/steps.py は web のセッションが API 越しに呼ぶ db の段(step.py)
randomizer/         db に触れない下書き作り(factory)と乱数
ai/                 AI に渡す文面と client
  instructions/     プロンプトに埋め込む基準の定数(Python)
  claude_code/      Claude Code(`claude -p`)の client と、検証(fact_checker)
gui/                データ編集 GUI。api/(FastAPI)と web/(Next.js)
tool/               危険操作(danger/)、テスト用の道具(test/。必ず手元の PostGIS のテスト用の db を使う。
                    mock_ai_client で AI 無しに生成を回す、seed_mock_db で全テーブルにモックデータを流し込む。テスト用の db は copy_production_db で本番を写して作る)、
                    AWS の RDS へ踏み台越しに繋ぐ aws/rds(--serve でふだんの転送、-- <コマンド> でマスターで流す)
web_session/        Claude Code on the web のセッションが呼ぶ流れ。claude -p を回し、db には API の段越しにだけ触る
                    (API に届くかを見る check_api)
infra/              AWS のリソース(CDK、TypeScript。npx cdk deploy)。既存の db・踏み台は作り直さず参照する
  lambda/           API を Lambda(Lambda Web Adapter)で動かすコンテナ。amplify.yml(ルート)は画面を Amplify で建てる設定
infra_local/        手元・クラウドのセッションで使う開発用のリソース(空の PostgreSQL + PostGIS を用意する postgis.sh)
```


# 成果物一覧


<https://syosetu.com/usernovelmanage/top/ncode/3323080/>