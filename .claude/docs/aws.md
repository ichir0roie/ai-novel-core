# AWS の db・資源と、API・web の流れの形

AWS の db(RDS for PostgreSQL、db `novel`)と資源に触れる作業、API(Lambda)の段と web のセッションの流れ(`web_session/`)のコードを書く作業の決まり。
資源の構成と手順は `.docs/aws-deploy.md`、待ち行列と web のセッションで回す仕組みは `.docs/claude-tasks.md`、db を読み書きする手順は、web のセッションは `.claude/docs/web-db.md`、手元は `.claude/docs/db.md`。

## core は公開リポジトリ

core(ai-novel-core)は公開リポジトリ。誰がクローンしても、自分の AWS アカウントに自分用に建てて使える形を保つ。

- core のコード・CDK・文書・テスト・コミットに、特定の構築の値を書かない。アカウント ID、リソースの ID(VPC・subnet・セキュリティグループ・インスタンス・EC2 Instance Connect Endpoint)、db のインスタンス名とエンドポイント、ARN、関数 URL、合言葉、自分の GitHub のリポジトリ名
- 文書では `<アカウント ID>` のような置き場所の印を使う
- アカウントとリージョンは、`cdk` を動かす人の AWS CLI のプロファイルから取る(`CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION`)
- 構築ごとの設定(使い回す既存のリソースの ID、CI を許す GitHub のリポジトリなど)は、構築するアカウントの SSM パラメータ `/novel/deploy/config` に JSON で置き、`infra/` が synth のときに読む。どのリポジトリにも置かない
- deploy のあとに決まる値(関数 URL など)も SSM の `/novel/*` に置き、使う側がそこから引く
- 既存のリソースの ID が設定に無ければ、`infra/` のスタックが自分で作る(NAT の無い VPC、小さな RDS、踏み台と EC2 Instance Connect Endpoint)
- CDK が手元に貯める `cdk.context.json` は、アカウントやリソースの ID を含むので git に入れない
- core にコミットする前に、差分を `grep -E '[0-9]{12}|vpc-|subnet-|sg-|i-0|eice-|arn:aws|rds\.amazonaws\.com|lambda-url'` などで見て、構築の値が紛れていないか確かめる

## 場所ごとの db への道

| 場所 | db への道 | db のロール | 持つ鍵 |
| --- | --- | --- | --- |
| 手元(CLI・VS Code) | 踏み台越しの転送(`tool.aws.rds --serve`、127.0.0.1:15432)。ふだんは IAM データベース認証(`DEM_DATABASE_IAM_AUTH=1`)。手で当てるマイグレーションは同じ転送で `novel_migrator` に IAM 認証で。管理(ロールを作るなど)は `tool.aws.rds --` 越しにマスターで | `novel_app`(ふだん)/ `novel_migrator`(マイグレーション)/ マスター(管理) | 手元の AWS CLI の権限(`rds-db:connect`・マスターの秘密の読み取り) |
| Lambda(`novel-migrate`) | VPC の中から psycopg で直に。IAM データベース認証。CI が `main` へのマージごとに呼び、`alembic upgrade head` だけを流す | `novel_migrator`(表の持ち主) | 実行ロールの `rds-db:connect` |
| Lambda(`novel-api`) | VPC の中から psycopg で直に。IAM データベース認証(`DEM_DATABASE_IAM_AUTH=1`) | `novel_app`(行の読み書きだけ) | 実行ロールの `rds-db:connect` |
| web のセッション(Claude Code on the web) | db には繋がない。`novel-api` の API のエンドポイントだけを呼ぶ | 無し | web 用の API の合言葉だけ |

## 決まり

1. マイグレーションは、`main` へのマージで CI(`deploy-api.yml`)が Lambda `novel-migrate` を呼んで AWS の db に当てる(`.docs/ci-cd.md` の「マイグレーション」)。中身は PR のレビューで見せる。
   - 手で当てる(CI を待たない・downgrade する)のは、ユーザに言われたときに、手元から `novel_migrator` でだけ行う(`.claude/docs/db.md` の「マイグレーションの確認」)
   - web のセッション・API の Lambda からは当てない。GitHub Actions に db への道やマスターの秘密を渡さない
2. API に、任意の SQL や、表を丸ごと消すような操作を受ける口を作らない。公開するのは `data_access_logic` の入口と、画面のための決まった操作だけ
3. `novel_app` に表を作る・変える権限(DDL)を与えない。表の形はマイグレーションだけが、表の持ち主の `novel_migrator` で変える(手元から当てるときも)。
   - マスターは表の持ち主でないので、マスターで alembic を流しても表を変えられない
   - マスターを `novel_migrator` の一員にしない(RDS が `rds_iam` を持つ側に数え、マスターがパスワードで入れなくなる)
   - これから増える表への `novel_app` の権限は、`novel_migrator` に掛けた既定の権限(`infra/sql/novel_migrator.sql`)で付く
4. AWS の資源は `infra/` の CDK で持つ。コンソールや CLI で直に作らない・変えない(状態を調べる読み取りはよい)。
   `cdk deploy` や資源を変える操作は、ユーザの承認を得てから行う。費用を抑えるため、NAT ゲートウェイや VPC のインターフェースエンドポイントを足さない
5. 鍵は呼ぶ側ごとに分ける。API の合言葉は画面(Amplify)用と web 用で別にする。web の環境には web 用の合言葉だけを置き、db のパスワードや AWS のアクセスキーは置かない
6. 関数 URL は SSM の `/novel/api/function-url`、合言葉は `/novel/api-keys/<gui|web>` から引く。合言葉の値はログや報告にも出さない

## web から AI の入口を回す形

処理の主体は Claude Code のセッション。Lambda の API は db とのやり取りだけを受け持つ。
web のセッションの側のコード(流れを持ち、`claude -p` を回し、Lambda の関数 URL を呼んで返事を受ける)は、手元の入口(`data_access_logic`)とは別の関数として `web_session/` に置く。

| 段 | どこで | 形 |
| --- | --- | --- |
| 材料を読む・出力を書く | API(Lambda) | db の段。`data_access_logic/<領域>/steps.py` の `@db_step` の関数を、`POST /api/steps/{id}` が一つのトランザクションで回し、終わりに commit する |
| AI を呼ぶ | web のセッション | `data_access_logic` の AI だけの関数(`*_draft` など)。材料を `*Serialized` に読み直して AI に渡す文面を作り、出力のモデルで受ける |
| 流れ | web のセッション | `web_session/<領域>.py`。db の段を API で呼び(`web_session/api.py`)、間で AI の段を回す。入口と同じ引数を取り、待ち行列からは `web_session/flows.py` の対応表で引く |

- 材料・出力・レスポンスは、どれも pydantic のモデルで受け渡す(`data-access.md` の方針)。API は受けた JSON を型注釈のモデルに validate してから使う。段の出力は土台のマテリアル(`*Serialized` でないもの)で宣言し、列のまま JSON にする
- 「AI の結果は得たらすぐ commit する」境界を保つ。AI の結果を書き戻す段を一回呼ぶのが一つの commit。段の中では commit しない
- 手元の入口も、同じ db だけの関数と AI だけの関数をつないで動く。違うのは、db の関数を自分のセッションで呼ぶか API で呼ぶかだけ
- web のセッションで待ち行列を回すのは、ユーザに頼まれたとき(スキル `run-ai-tasks`)。スケジュールで起こすルーチンは使わない
- claude を叩く入口を足したら、段と web の流れも足す(`.docs/claude-tasks.md` の「claude を叩く入口を足すとき」)
