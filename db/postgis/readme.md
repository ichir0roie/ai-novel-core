# PostGIS で場所を問い合わせる

`novel.db`(sqlite)を PostGIS へ写し、場所の経緯度・輪郭を空間の問い合わせで引けるようにする。
正は sqlite のまま。PostGIS 側は写しなので、直すのは sqlite の方にして写し直す。

## 立てる

どちらか一つ。

- docker: `docker compose -f core/db/postgis/compose.yaml up -d`(ユーザ・パスワード・db はどれも `novel`)
- 手元の PostgreSQL: postgis の拡張を入れ(Ubuntu なら `apt install postgresql-16-postgis-3`)、
  superuser で `CREATE EXTENSION postgis` を打った db を用意する

## 写す

世界リポジトリのルートで、ほかの python と同じく `DEM_WORLD_DIR` と `PYTHONPATH` を渡して打つ。
写し元は `db/schema.py` の `DB_PATH`(`DEM_DB_PATH` で差し替えられる)。

```
python -m db.postgis.copy_to_postgis
```

写し先は `--url`、無ければ環境変数 `DEM_POSTGIS_URL`、それも無ければ compose の db
(`postgresql+psycopg://novel:novel@localhost:5432/novel`)。写し先の表は毎回消して作り直す。

表と列は `db/schema.py` のとおりで、`location` にだけ次の生成列(と GiST の索引)が付く。

| 列 | 中身 |
| --- | --- |
| `geom` | `location_longitude` / `location_latitude` の点(`geometry(Point, 4326)`) |
| `outline` | `polygon` の輪郭(`geometry(Polygon, 4326)`) |

架空の星でも SRID は地球の 4326 を借りている。距離・面積は星の半径(星の行の `area` から出す)で測り直す。

## 問い合わせる

例は `queries.sql`(近い場所・点を含む輪郭・輪郭の広さ)。

```
psql -h localhost -U novel -d novel -v origin_id=1 -v lon=135.5 -v lat=35.0 -f core/db/postgis/queries.sql
```

sqlite は外部キーを確かめないので、消えた行を指したままの列があると、写すときに外部キー違反で止まる。
そのときは sqlite の方で指す先を直してから写し直す。
