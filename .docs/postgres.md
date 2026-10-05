# PostgreSQL + PostGIS

db は PostgreSQL + PostGIS。本番は AWS の RDS ただ一つで、開発とテストは手元に作った PostgreSQL + PostGIS を使う。
`db/schema.py` が唯一の正で、どの db を読み書きするかは環境変数で決まる。

| 環境変数 | 意味 |
| --- | --- |
| `DEM_DATABASE_URL` | 読み書きする db の SQLAlchemy の URL。手元のふだんは踏み台越しの RDS(`.claude/docs/setup.md`) |
| `DEM_DATABASE_IAM_AUTH` | `1` なら、パスワードの代わりに RDS の IAM データベース認証のトークンで繋ぐ(Lambda と手元のふだん) |
| `DEM_DEV_DATABASE_URL` | 開発用の空の db(下の「開発用の db」)。無ければテスト(`tool.test`)が用意する |

テスト(`tool.test` を読むもの)は `DEM_DATABASE_URL` を手元のテスト用の db(`novel_test`)に差し替える。本番の RDS には書かない。

## 空の db を作る

PostGIS の入ったサーバー(RDS for PostgreSQL・ローカルの `postgresql-16-postgis-3` など)に対して、リポジトリのルートで:

```
.venv/bin/python -m db.postgres.init_db --url 'postgresql+psycopg://novel:***@host:5432/novel' --create-database
```

- `--create-database` は、URL の db が無ければ同じサーバーの `postgres` db に繋いで `CREATE DATABASE`(UTF8)する
- `CREATE EXTENSION postgis` → `schema.py` の全表 → マスター(`personality_level`)→ PostGIS の生成列 → alembic を head に stamp
- 表が一つでもあれば止まる。作り直すなら db ごと消してからやり直す
- 過去のマイグレーション(SQLite 向けに積んできた `batch_alter_table`)は流さない。今の形を `schema.py` から作る
- AWS の db へは、URL を自分で書かずに踏み台越しにマスターで流す:
  `.venv/bin/python -m tool.aws.rds -- .venv/bin/python -m db.postgres.init_db --create-database`([aws-deploy.md](aws-deploy.md#手元から-db-へ繋ぐ))

## 開発用の db

開発では、手元に作った空の PostgreSQL + PostGIS の db を使う。`infra_local/postgis.sh` がサーバーを用意して起動し、
db(`novel_dev`)が無ければ上の `init_db --create-database` で作って、その URL を標準出力に出す。何度走らせてもよい。

| 動く所 | サーバー | URL |
| --- | --- | --- |
| Claude Code on the web(`CLAUDE_CODE_REMOTE=true`) | apt で入れた既定のクラスタ(初回は入れるのに 1 分半ほど) | `postgresql+psycopg://novel:novel@127.0.0.1:5432/novel_dev` |
| それ以外(手元の端末) | Docker のコンテナ `novel-postgis`(`postgis/postgis:16-3.5`、中身はボリューム `novel-postgis-data`) | `postgresql+psycopg://novel:novel@127.0.0.1:55432/novel_dev` |

SessionStart フックは呼ばない。`DEM_DEV_DATABASE_URL` が渡されていなければ、テスト(`tool.test`)が要ったときにこれを呼んで用意する。手で使うときは
`DEM_DEV_DATABASE_URL=${DEM_DEV_DATABASE_URL:-$(infra_local/postgis.sh .venv/bin/python)}` で受ける。`DEM_DATABASE_URL`(本番)は変えないので、
開発で動かすときに渡す:

```
DEM_DATABASE_URL="$DEM_DEV_DATABASE_URL" DEM_DATABASE_IAM_AUTH=0 .venv/bin/python -m ...
```

- `core` の変更で列が増えたら、同じように開発用の db の URL を渡して `alembic upgrade head` を当てる(フックは当てない)
- 空に戻すときは db を消す(`docker exec novel-postgis dropdb -U novel novel_dev`、クラウドは `runuser -u postgres -- dropdb novel_dev`)。次にスクリプトを走らせると作り直す
- テスト用の db(`novel_test`)も同じサーバーに作る。テストの始めに、無いか空のときだけ本番を写して作る(`tool.test.ensure_test_db`)。
  作り直すときは `.venv/bin/python -m tool.test.recreate_db`(消して本番を写し直す)

## db から db へ写す

```
.venv/bin/python -m db.postgres.copy_db --source-url <写し元の URL> --url <写し先の URL>
```

テスト用の db に本番を写すのもこれ(`tool.test.copy_production_db`)。以前は SQLite の `novel.db` を写し元にでき、本番を RDS へ移したのもこれ(SQLite を読む分岐は、移し終えたので消した)。

- 写し元・写し先の alembic のバージョンが違えば止まる
- 写し先に行があれば止まる(`--truncate` で空にしてから写す)
- 自分の表を指す外部キー(`location.parent_id` など)は、親が後ろの id にあっても入るよう、いったん空で入れて後から埋める
- 値は型を通さず生のまま運ぶ。PostGIS の生成列は写さない。最後に連番(`id`)を最大値へ寄せ、件数を突き合わせる
- 全部を一つのトランザクションで写すので、途中で落ちれば何も入らない

`novel.db` の写し(84 場所・118 人物・50 話ほど)で、写したあとの API の応答(334 の GET と読み取りの入口)が
SQLite と PostgreSQL で一致することを確かめてある。`novel.db` を切り離す前に、RDS の 24 表の全行が `novel.db` と一致することも確かめた。

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

距離・面積は星の大きさで読み替える。星の半径は、星の行(`kind = '星'`。`location_planet` はその `id` を指す)の `area`(表面積 km²)から
`sqrt(area / 4π)` で出す(`data_access_logic/map/geometry.py` の `planet_radius_km` と同じ決め方。地球の 510,072,000 → 約 6,371 km)。

```sql
-- :origin_id と同じ星にある場所を近い順に(ListNeighbors と同じ並び)。
-- 方角は回転楕円体の上で測るので、球で測る ListNeighbors と 1 度ほどずれることがある
SELECT near.id, near.name, near.kind,
       round((ST_DistanceSphere(origin.geom_point, near.geom_point, sqrt(planet.area::float8 / (4 * pi())) * 1000) / 1000)::numeric)
           AS distance_km,
       round(degrees(ST_Azimuth(origin.geom_point::geography, near.geom_point::geography))::numeric) AS bearing_deg
FROM location origin
JOIN location planet ON planet.id = origin.location_planet
JOIN location near ON near.location_planet = origin.location_planet AND near.id <> origin.id
WHERE origin.id = :origin_id AND near.geom_point IS NOT NULL
ORDER BY distance_km, near.id
LIMIT 10;

-- 点の場所ごとに、それを輪郭に含む同じ星の場所。経緯度の平面で判定するので、極や経度 ±180 をまたぐ輪郭では外れる
SELECT point.id, point.name, area.id AS area_id, area.name AS area_name
FROM location point
JOIN location area ON area.location_planet = point.location_planet AND area.id <> point.id
    AND ST_Covers(area.geom_shape, point.geom_point)
ORDER BY point.id;

-- 輪郭の広さ(km²)。地球の球の上で測った広さを、星と地球の半径の比の二乗で伸び縮みさせる
SELECT area.id, area.name,
       round((ST_Area(area.geom_shape::geography, false) / 1e6
              * (planet.area::float8 / (4 * pi())) / (6371.0088 ^ 2))::numeric) AS shape_km2,
       area.area
FROM location area
JOIN location planet ON planet.id = area.location_planet
WHERE area.geom_shape IS NOT NULL;
```

alembic の autogenerate は、これらの列・索引と PostGIS の `spatial_ref_sys` を消そうとしない(`db/alembic/env.py` の `include_object`)。

## SQLite との違いで直したところ

以前は SQLite(`novel.db`)でも動かしていた。そのときに PostgreSQL との違いで直したところ。SQLite 向けの分岐は、RDS へ移し終えたので消した。

| 違い | 直し方 |
| --- | --- |
| PostgreSQL の `json` は等値が無く、行ごとの `DISTINCT` で落ちる | `polygon` は `jsonb`(`PolygonType`) |
| NULL の並び(SQLite は最小、PostgreSQL は最大) | NULL を持てる列の並びに、SQLite と同じ向き(降順は `.nulls_last()`、昇順は `.nulls_first()`)を明示(人物の居場所・来歴・出来事・呼び名のリレーション、`character_location_select`、`episode/summary.py`) |
| `DISTINCT` の並び(PostgreSQL は崩れる) | 居合わせる人物の id(`resident_character_ids_select`)を id の順に並べる |
| `boolean` に 0/1 を入れられない | 移すときに `bool` に直した |
| ALTER の強さ | alembic は SQLite でだけ batch(表の作り直し)で書いていた |

## マイグレーション

`schema.py` を変えたら、開発用の db に対して `revision --autogenerate` → 確認 → `upgrade head` を回す
(`DEM_DATABASE_URL="$DEM_DEV_DATABASE_URL" DEM_DATABASE_IAM_AUTH=0 .venv/bin/python -m alembic -c db/alembic/alembic.ini ...`)。
同じファイルを RDS にも当てる。表を変えるのでマスターで流す(手順は [ci-cd.md](ci-cd.md#マイグレーション))。

## 接続

Lambda は凍結をはさんで接続を使い回し、手元の転送は 1 時間ごとに張り直すので、PostgreSQL の engine は `pool_pre_ping=True`・`pool_recycle=300` で作る
(`db/schema.py` の `make_url_engine`)。ドライバは `psycopg`(`requirements.txt`)。
