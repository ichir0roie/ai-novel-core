# 費用の見直し

AWS の費用を下げる手を検討した覚え書き。金額は東京リージョンの定価からの概算で、実際の請求(Cost Explorer)で確かめたものではない。
決める前に、Cost Explorer のサービス別・使用タイプ別の内訳を見る。

## db(RDS)

今は RDS for PostgreSQL の db.t4g.micro・20 GB(シングル AZ)で、本体 月 $18 ほど + ストレージ 月 $3 ほど ≒ **月 $21**。

| 手 | 月額の目安 | 手間 | 失うもの |
| --- | --- | --- | --- |
| RDS のリザーブドインスタンス(1 年・前払い無し) | 3〜4 割引で $13 前後 | 買うだけ。構成は変えない | 1 年の縛り |
| EC2 に自分で PostgreSQL + PostGIS を建て、毎日 S3 へバックアップ | t4g.micro + EBS gp3 20 GB で $10 前後 | 大きい(下の「EC2 に移すとき」) | どの時点にも戻せる復元(RDS は 5 分単位)、パッチ・障害対応を AWS に任せること |
| Aurora Serverless v2(0 ACU まで下げる) | 使っている時間だけ。止まっている間はストレージ代だけ | EC2 と同じくらい | 起きるのに十数秒。Lambda のタイムアウト(30 秒)にぎりぎり |

進め方: まずリザーブドインスタンスで足りるかを見る。それでも高ければ EC2 に移す。

### EC2 に移すとき

- t4g.nano(メモリ 0.5 GB)は PostGIS 入りの PostgreSQL には足りない。t4g.micro を下限にする
- IAM データベース認証は RDS だけの機能。Lambda と `tool.aws.rds --serve`(`DEM_DATABASE_IAM_AUTH=1`)はパスワードで繋ぐ形に直す。
  Lambda は Secrets Manager に届かない(NAT が無い)ので、パスワードは API の合言葉と同じく `cdk deploy` のときに環境変数へ入れる
- `tool.aws.rds` のマスターの接続(RDS が管理する秘密を読む)も直す
- isolated subnet の EC2 はインターネットに出られない。PostGIS は Amazon Linux 2023 の公式のリポジトリに無いはずなので、
  入れる道を用意する(IPv6 の egress-only インターネットゲートウェイは無料。または建てるときだけ外に出す)
- S3 へは S3 のゲートウェイエンドポイント(無料)で届く。インターフェースエンドポイントは要らない
- バックアップ: systemd のタイマーで毎日 `pg_dump -Fc` を S3 に置き、S3 のライフサイクルで古いものを消す。
  速く戻すために EBS のスナップショット(Data Lifecycle Manager)も併せて取る。最悪で 1 日分を失う
- db の EC2 が踏み台を兼ねられるので、今の踏み台(t4g.nano)と、それを起こす手順は要らなくなる
- 資源は今と同じく `infra/` の CDK で持つ(`NovelData` の `rds.DatabaseInstance` と SSM の `/novel/db/*` を差し替える)。
  移すときは RDS から `pg_dump` して EC2 へ流し込む

## main へのマージごとのデプロイ

| 掛かるもの | 目安 |
| --- | --- |
| GitHub Actions(`deploy-api.yml`) | 公開リポジトリなので無料 |
| Lambda のコードの差し替え | 無料 |
| ECR のイメージ(新しい 30 個を残す) | 容量次第で月に数十セント〜$1 ほど |
| Amplify のビルド(`main` への push ごと) | ビルド 1 分 $0.01。Next.js で 3〜5 分なら一回 $0.03〜0.05 |

一回あたりは数セントのはず。これより明らかに大きければ、ほかに原因がある。減らすなら:

- Amplify の自動ビルドを切り、手で(または webhook で)建てる。効きが一番大きい
- `deploy-api.yml` のきっかけを `main` への push から、手動(`workflow_dispatch`)やタグの push に替え、マージを溜めてまとめて出す
- ECR に残すイメージを 30 個から 5 個ほどに減らす(`infra/lib/ci-stack.ts` のライフサイクル)
