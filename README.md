# ai-novel-core

AI にラノベを書いてもらうためのプロジェクト。
これで生成されるデータは他のリポジトリに配置する。プライベートな。ぐく

## 特徴

- **世界が先、本文が後。** 場所・人物・人物相関・出来事・アイデアをすべて `novel.db` に記録し、
  本文(`episode`)はその時点・その場所の断面を引いてから書く
- **AI が世界を組み立てる。** 作者の下書きを核に、人物・出来事・話を Claude Code(`claude -p`)に生成させて db に積む
- **db に触れる処理を一本化。** db を読み書きする処理と入口は `data_access_logic/` にまとめ、Claude(CLI)も GUI の API も同じ入口を呼ぶ。
  下書きを「作る」側は db に触れず下書きのモデルを返し、「確定する」側が実在確認とスキーマの検証をして書き込む
- **GUI で読める・直せる。** `gui/`(FastAPI + Next.js)で一覧・修正・追加と、未確認のアイデア・ミームのレビュー、
  星ごとの地図(svg / html)と人物相関図を見る
- **本文は種から書く。** 話ごとに作者が `key`(場面割りと狙い)を置き、AI か作者が本文(`episode`)を書く
- **時間に上限がない。** 年は何桁でもよく(ノウル一万年代など)、遠未来の世界線も同じ仕組みで扱う
- **テストは本番に触れない。** `novel.test.db` とモック AI で、AI 無しに生成を回せる



## ディレクトリ

| ディレクトリ     | 役割                                                          |
| ---------------- | ------------------------------------------------------------- |
| `db/` `ai/` ほか | 仕組み。db の形・入口・問い合わせ・AI の client               |
| `../novel.db`    | **世界の記録と本文そのもの**(SQLite。世界リポジトリ側)        |
| `gui/`           | データ編集 GUI(API と画面)。使い方は `gui/readme.md`         |
| `CLAUDE.md`      | **Claude 向けの作業指針**                                     |

```
db/                 **記録の形(SQLAlchemy)。列はここ一か所で決まる**
                    alembic/ にマイグレーション
data_access_logic/  **db を読み書きする処理と入口。db に触れるのはここ越しだけ**(一覧は data_access_logic/readme.md)
                    location/ character/ event/ event_seed/ story/ episode/ idea/ meme/ oracle/ review/ fact_check/ map/ query/
randomizer/         db に触れない下書き作り(factory)と乱数
ai/                 AI に渡す文面と client
  instructions/     プロンプトに埋め込む基準の定数(Python)
  claude_code/      Claude Code(`claude -p`)の client と、検証(fact_checker)
gui/                データ編集 GUI。api/(FastAPI)と web/(Next.js)
tool/               危険操作(danger/)、テスト用の道具(test/。必ず novel.test.db を使う。
                    mock_ai_client で AI 無しに生成を回す、seed_mock_db で全テーブルにモックデータを流し込む。novel.test.db は copy_novel_db で本番の novel.db を写して作る)
```


# 成果物一覧


<https://syosetu.com/usernovelmanage/top/ncode/3323080/>