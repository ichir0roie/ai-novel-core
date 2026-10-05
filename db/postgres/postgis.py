#!/usr/bin/env python3
"""PostgreSQL 側だけに足す PostGIS の物。

列の正は `db/schema.py` に一つだけ置き、PostGIS の幾何はそこから作る生成列にする。
書き込みは今まで通り経度・緯度(`location_longitude` / `location_latitude`)と輪郭(`polygon`。GeoJSON)だけに行い、
幾何の列は db が作り直すので、コードから書かない。範囲・距離の検索や GIS の道具で覗くときにだけ使う。

座標は星ごとの経緯度(`location_planet` で星を分ける)なので、SRID は 4326(経緯度の度)として持つだけで、
地球以外の星で距離(m)を測るときは星の大きさで読み替える。
"""
from __future__ import annotations

from sqlalchemy import Connection, text

# schema.py に無い、PostGIS が足す表・この仕組みが足す列。alembic の autogenerate はこれらを消そうとしない
POSTGIS_TABLES = frozenset({"spatial_ref_sys"})
POSTGIS_COLUMNS = frozenset({("location", "geom_point"), ("location", "geom_shape")})

_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS postgis",
    """
    ALTER TABLE location ADD COLUMN IF NOT EXISTS geom_point geometry(Point, 4326)
    GENERATED ALWAYS AS (
        CASE WHEN location_longitude IS NOT NULL AND location_latitude IS NOT NULL
             THEN ST_SetSRID(ST_MakePoint(location_longitude::float8, location_latitude::float8), 4326)
        END) STORED
    """,
    """
    ALTER TABLE location ADD COLUMN IF NOT EXISTS geom_shape geometry(Polygon, 4326)
    GENERATED ALWAYS AS (
        CASE WHEN jsonb_typeof(polygon) = 'object'
             THEN ST_SetSRID(ST_GeomFromGeoJSON(polygon::text), 4326)
        END) STORED
    """,
    "CREATE INDEX IF NOT EXISTS ix_postgis_location_geom_point ON location USING gist (geom_point)",
    "CREATE INDEX IF NOT EXISTS ix_postgis_location_geom_shape ON location USING gist (geom_shape)",
)


def install_postgis(conn: Connection) -> None:
    """何度打っても同じになる(IF NOT EXISTS)。`location` の表を作ったあとに呼ぶ。"""
    for statement in _STATEMENTS:
        conn.execute(text(statement))
