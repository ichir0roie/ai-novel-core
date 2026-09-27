# ai-novel-core

AI にラノベを書いてもらうためのプロジェクト。
これで生成されるデータは他のリポジトリに配置する。プライベートな。ぐく

## 特徴

- **世界が先、本文が後。** 場所・人物・人物相関・出来事・アイデアをすべて `novel.db` に記録し、
  本文(`episode`)はその時点・その場所の断面を引いてから書く
- **AI が自動で世界を進める。** 常駐ループ(`ai/time_keeper/`)が時間を進め、
  人物の誕生・寿命、出来事、場所を生成して db に積む
- **AI を差し替えられる。** 同じループをローカル AI(Ollama)でも Claude Code(`claude -p`)でも回せる
- **db に触れる入口を一本化。** Claude は `ai/claude_code/interface/` の入口越しにだけ読み書きする。
  下書きを「作る」側は db に触れず辞書を返し、「確定する」側が実在確認と列チェックをして書き込む
- **GUI で読める・直せる。** `gui/`(FastAPI + Next.js)で一覧・修正・追加と、未確認のアイデア・ミームのレビュー、
  星ごとの地図(svg / html)と人物相関図を見る
- **本文は種から書く。** 話ごとに作者が `key`(場面割りと狙い)を置き、AI か作者が本文(`episode`)を書く
- **時間に上限がない。** 年は何桁でもよく(ノウル一万年代など)、遠未来の世界線も同じ仕組みで扱う
- **テストは本番に触れない。** `novel.test.db` とモック AI で、AI 無しにループを再走できる



## ディレクトリ

| ディレクトリ     | 役割                                                          |
| ---------------- | ------------------------------------------------------------- |
| `db/` `ai/` ほか | 仕組み。db の形・入口・問い合わせ・ローカル AI                |
| `../novel.db`    | **世界の記録と本文そのもの**(SQLite。世界リポジトリ側)        |
| `gui/`           | データ編集 GUI(API と画面)。使い方は `gui/readme.md`         |
| `CLAUDE.md`      | **Claude 向けの作業指針**                                     |

```
db/                 **記録の形(SQLAlchemy)。列はここ一か所で決まる**
                    alembic/ にマイグレーション
data_access_logic/  引き方(Select の組み立て)。SQL 文字列は組まない
randomizer/         db に触れない下書き作り(factory)と乱数
ai/                 AI に生成させる側をまとめた置き場
  instructions/     常駐ループのプロンプトに埋め込む基準の定数(Python)
  time_keeper/      常駐ループの本体。世界を進める生成器(人物・出来事・場所・寿命)。AI は引数で受け取る
  local_ai/         ローカル AI(Ollama)の client と、それでループを回す入口
  claude_code/      Claude Code(`claude -p`)の client と、それでループを回す入口。本文(episode)もここが書く
    interface/      **Claude が呼ぶ入口。db に触れるのはここ越しだけ**
                    randomizer/ story/ world/ meme/ idea/ review/ fact_check/
gui/                データ編集 GUI。api/(FastAPI)と web/(Next.js)
tool/               地図(map/)・人物相関図(relation/)の描画、危険操作(danger/)、テスト用の道具(test/。必ず novel.test.db を使う。
                    mock_ai_client で AI 無しに redrive_mock_world を回す、seed_mock_db で全テーブルにモックデータを流し込む)
```


# 成果物一覧


<https://syosetu.com/usernovelmanage/top/ncode/3323080/>