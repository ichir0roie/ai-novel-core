#!/usr/bin/env python3
"""`novel.db`(sqlite)の中身を PostGIS へまるごと写す。写し先の表は毎回作り直す。

正は sqlite のまま。PostGIS 側は空間の問い合わせを試すための写しなので、直すのは sqlite の方にして写し直す。
"""
from __future__ import annotations

import argparse
import logging
import os

from sqlalchemy import Connection, Table, bindparam, create_engine, make_url, select, text, update

from db.schema import DB_PATH, Base, engine as sqlite_engine

logger = logging.getLogger(__name__)

DEFAULT_URL = "postgresql+psycopg://novel:novel@localhost:5432/novel"

# 架空の星でも経緯度の並びは GeoJSON と同じなので、SRID は地球の 4326 を借りる。
# 距離・面積は 4326 の地球の大きさで出るので、星の半径で測り直す(queries.sql)。
# 元の列から作る生成列なので、sqlite から写すときも写した後も手で書かない。
SPATIAL_DDL = (
    "ALTER TABLE location ADD COLUMN geom geometry(Point, 4326) GENERATED ALWAYS AS"
    " (ST_SetSRID(ST_MakePoint(location_longitude::float8, location_latitude::float8), 4326)) STORED",
    "ALTER TABLE location ADD COLUMN outline geometry(Polygon, 4326) GENERATED ALWAYS AS"
    " (ST_SetSRID(ST_GeomFromGeoJSON(polygon::text), 4326)) STORED",
    "CREATE INDEX ix_location_geom ON location USING gist (geom)",
    "CREATE INDEX ix_location_outline ON location USING gist (outline)",
)


def self_referencing_columns(table: Table) -> list[str]:
    return [column.name for column in table.columns
            if any(foreign_key.column.table is table for foreign_key in column.foreign_keys)]


def copy_table(source: Connection, target: Connection, table: Table) -> int:
    rows = [dict(row) for row in source.execute(select(table)).mappings()]
    if not rows:
        return 0
    # 親を指す列は、指す先の行が同じ表の後ろにあることがあるので、全行を入れてから埋める
    parent_columns = self_referencing_columns(table)
    target.execute(table.insert(), [{**row, **dict.fromkeys(parent_columns)} for row in rows])
    for column in parent_columns:
        links = [{"row_id": row["id"], "value": row[column]} for row in rows if row[column] is not None]
        if links:
            target.execute(update(table).where(table.c.id == bindparam("row_id"))
                           .values({column: bindparam("value")}), links)
    # id を明示して入れたので、次に足す行の id が重ならないよう連番を進める
    target.execute(text("SELECT setval(pg_get_serial_sequence(:name, 'id'), (SELECT max(id) FROM {}))"
                        .format(target.dialect.identifier_preparer.quote(table.name))), {"name": table.name})
    return len(rows)


def copy_to_postgis(url: str) -> dict[str, int]:
    target_engine = create_engine(url)
    counts = {}
    # 一つのトランザクションで作り直すので、途中で落ちても前の写しが残る
    with sqlite_engine.connect() as source, target_engine.begin() as target:
        target.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        Base.metadata.drop_all(target)
        Base.metadata.create_all(target)
        for table in Base.metadata.sorted_tables:
            counts[table.name] = copy_table(source, target, table)
            logger.info("%s: %d 行", table.name, counts[table.name])
        for statement in SPATIAL_DDL:
            target.execute(text(statement))
    target_engine.dispose()
    return counts


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=os.environ.get("DEM_POSTGIS_URL", DEFAULT_URL),
                   help="写し先(SQLAlchemy の URL)。既定は環境変数 DEM_POSTGIS_URL、無ければ compose.yaml の db")
    args = p.parse_args()
    logger.info("%s → %s", os.path.abspath(DB_PATH), make_url(args.url).render_as_string(hide_password=True))
    for name, count in copy_to_postgis(args.url).items():
        print(f"{name}\t{count}")


if __name__ == "__main__":
    main()
