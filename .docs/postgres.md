# PostgreSQL + PostGIS

`db/schema.py` を唯一の正のまま、SQLite(`novel.db`)と PostgreSQL のどちらでも動くようにしてある。
どちらを使うかは環境変数で決まる。

| 環境変数 | 意味 |
| --- | --- |
| `DEM_DATABASE_URL` | PostgreSQL の SQLAlchemy の URL(例: `postgresql+psycopg://novel:***@host:5432/novel`)。あれば SQLite より優先する |
| `DEM_DB_PATH` / `DEM_NOVEL_DB_PATH` | 今までどおりの SQLite のファイル。`DEM_DATABASE_URL` が無いときに使う |

テスト(`tool.test` を読むもの)は `DEM_DATABASE_URL` を消して必ず `novel.test.db` を使う。本番の PostgreSQL には書かない。

## 空の db を作る

PostGIS の入ったサーバー(RDS for PostgreSQL・ローカルの `postgresql-16-postgis-3` など)に対して、
世界リポジトリのルートで:

```
export DEM_WORLD_DIR="$PWD" PYTHONPATH="$PWD/core"
export DEM_DATABASE_URL='postgresql+psycopg://novel:***@host:5432/novel'
.venv/bin/python -m db.postgres.init_db --create-database
```

- `--create-database` は、URL の db が無ければ同じサーバーの `postgres` db に繋いで `CREATE DATABASE`(UTF8)する
- `CREATE EXTENSION postgis` → `schema.py` の全表 → マスター(`personality_level`)→ PostGIS の生成列 → alembic を head に stamp
- 表が一つでもあれば止まる。作り直すなら db ごと消してからやり直す
- 過去のマイグレーション(SQLite 向けに積んできた `batch_alter_table`)は流さない。今の形を `schema.py` から作る
- AWS の db へは、`DEM_DATABASE_URL` を自分で書かずに踏み台越しに流す:
  `.venv/bin/python -m tool.aws.rds -- .venv/bin/python -m db.postgres.init_db --create-database`([aws-deploy.md](aws-deploy.md#手元から-db-へ繋ぐ))

## 開発用の db

開発では、手元に作った空の PostgreSQL + PostGIS の db を使う。`infra_local/postgis.sh` がサーバーを用意して起動し、
db(`novel_dev`)が無ければ上の `init_db --create-database` で作って、その URL を標準出力に出す。何度走らせてもよい。

| 動く所 | サーバー | URL |
| --- | --- | --- |
| Claude Code on the web(`CLAUDE_CODE_REMOTE=true`) | apt で入れた既定のクラスタ(初回は入れるのに 1 分半ほど) | `postgresql+psycopg://novel:novel@127.0.0.1:5432/novel_dev` |
| それ以外(手元の端末) | Docker のコンテナ `novel-postgis`(`postgis/postgis:16-3.5`、中身はボリューム `novel-postgis-data`) | `postgresql+psycopg://novel:novel@127.0.0.1:55432/novel_dev` |

世界リポジトリの SessionStart フックがこれを呼び、URL を `DEM_DEV_DATABASE_URL` に渡す。`DEM_DATABASE_URL` は変えないので、
執筆(`novel.db`)の作業には影響しない。開発で動かすときに渡す:

```
DEM_DATABASE_URL="$DEM_DEV_DATABASE_URL" .venv/bin/python -m ...
```

- `core` の変更で列が増えたら、同じように `DEM_DATABASE_URL="$DEM_DEV_DATABASE_URL"` を渡して `alembic upgrade head` を当てる(フックは当てない)
- 空に戻すときは db を消す(`docker exec novel-postgis dropdb -U novel novel_dev`、クラウドは `runuser -u postgres -- dropdb novel_dev`)。次にスクリプトを走らせると作り直す
- テスト(`tool.test`)は今までどおり `novel.test.db` を使う

## novel.db の中身を移す

```
.venv/bin/python -m alembic -c core/db/alembic/alembic.ini upgrade head   # 先に novel.db を head へ(DEM_DATABASE_URL を外して)
.venv/bin/python -m db.postgres.import_sqlite                               # 写し元は DEM_NOVEL_DB_PATH(既定 <世界>/novel.db)
```

- 写し元・写し先の alembic の版が違えば止まる
- 写し先に行があれば止まる(`--truncate` で空にしてから写す)
- SQLite は外部キーを確かめないので、指す先の無い行があれば写す前に一覧を出して止まる
- 自分の表を指す外部キー(`location.parent_id` など)は、親が後ろの id にあっても入るよう、いったん空で入れて後から埋める
- 値は型を通さず生のまま運び、真偽(0/1)だけ `boolean` に直す。最後に連番(`id`)を最大値へ寄せ、件数を突き合わせる
- 全部を一つのトランザクションで写すので、途中で落ちれば何も入らない

手元の `novel.db` の写し(84 場所・118 人物・50 話ほど)で、写したあとの API の応答(334 の GET と読み取りの入口)が
SQLite と PostgreSQL で一致することを確かめてある。

## PostGIS

列の正は `schema.py` に置き、PostGIS の幾何は `db/postgres/postgis.py` が PostgreSQL 側だけに足す生成列にする。
コードは今までどおり経度・緯度と `polygon`(GeoJSON)だけを書き、幾何は db が作り直す。

| 列 | 中身 |
| --- | --- |
| `location.geom_point` | `geometry(Point, 4326)`。`location_longitude` / `location_latitude` から |
| `location.geom_shape` | `geometry(Polygon, 4326)`。`polygon`(jsonb)から |

どちらも GiST の索引を張る(`ix_postgis_*`)。座標は星ごとの経緯度なので、`location_planet` で星を絞ってから使う。
SRID 4326 は「経緯度の度」として借りているだけで、地球以外の星の距離(m)は星の大きさで読み替える。

```sql
-- 地下世界ネザル(id 7)の代表点を含む輪郭
SELECT name FROM location WHERE ST_Contains(geom_shape, (SELECT geom_point FROM location WHERE id = 7));
```

alembic の autogenerate は、これらの列・索引と PostGIS の `spatial_ref_sys` を消そうとしない(`db/alembic/env.py` の `include_object`)。

## 二つの db の違いで直したところ

| 違い | 直し方 |
| --- | --- |
| PostgreSQL の `json` は等値が無く、行ごとの `DISTINCT` で落ちる | `polygon` は PostgreSQL では `jsonb`(`PolygonType.load_dialect_impl`) |
| NULL の並び(SQLite は最小、PostgreSQL は最大) | NULL を持てる列の並びに、SQLite と同じ向き(降順は `.nulls_last()`、昇順は `.nulls_first()`)を明示(人物の居場所・来歴・出来事・呼び名のリレーション、`character_location_select`、`episode/summary.py`) |
| `DISTINCT` の並び(PostgreSQL は崩れる) | 居合わせる人物の id(`resident_character_ids_select`)を id の順に並べる |
| `boolean` に 0/1 を入れられない | 移すときに `bool` に直す |
| ALTER の強さ | alembic は SQLite でだけ batch(表の作り直し)で書く |

## マイグレーション

`schema.py` を変えたら今までどおり SQLite の `novel.db` に対して `revision --autogenerate` → 確認 → `upgrade head`。
同じファイルを PostgreSQL にも当てる(`DEM_DATABASE_URL` を渡して `upgrade head`)。`batch_alter_table` は
PostgreSQL ではそのまま ALTER になるので、同じマイグレーションが両方で通る。
PostgreSQL に当てる手順は [ci-cd.md](ci-cd.md#マイグレーション) を見る。

## 接続

Lambda は凍結をはさんで接続を使い回すので、PostgreSQL の engine は `pool_pre_ping=True`・`pool_recycle=300` で作る
(`db/schema.py` の `make_url_engine`)。ドライバは `psycopg`(`requirements.txt`)。
