-- copy_to_postgis.py で写した db に打つ問い合わせの例。
-- psql -d novel -v origin_id=1 -v lon=135.5 -v lat=35.0 -f core/db/postgis/queries.sql
--
-- 距離・面積は星の半径で測る。半径は星の行(location_planet が指す行)の area(表面積 km²)から出す
-- (data_access_logic/map/geometry.py の planet_radius_km と同じ決め方。地球の 510,072,000 → 約 6,371 km)。

-- 1. :origin_id と同じ星にある場所を近い順に(ListNeighbors と同じ並び)。
--    方角は回転楕円体の上で測るので、球で測る ListNeighbors と 1 度ほどずれることがある
SELECT near.id, near.name, near.kind,
       round((ST_DistanceSphere(origin.geom, near.geom, sqrt(planet.area::float8 / (4 * pi())) * 1000) / 1000)::numeric)
           AS distance_km,
       round(degrees(ST_Azimuth(origin.geom::geography, near.geom::geography))::numeric) AS bearing_deg
FROM location origin
JOIN location planet ON planet.id = origin.location_planet
JOIN location near ON near.location_planet = origin.location_planet AND near.id <> origin.id
WHERE origin.id = :origin_id AND near.geom IS NOT NULL
ORDER BY distance_km, near.id
LIMIT 10;

-- 2. 点 (:lon, :lat) を輪郭に含む場所。経緯度の平面で判定するので、極や経度 ±180 をまたぐ輪郭では外れる
SELECT id, name, kind, location_planet
FROM location
WHERE ST_Covers(outline, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326));

-- 3. 点の場所ごとに、それを輪郭に含む同じ星の面の場所
SELECT point.id, point.name, area.id AS area_id, area.name AS area_name
FROM location point
JOIN location area ON area.location_planet = point.location_planet AND area.id <> point.id
    AND ST_Covers(area.outline, point.geom)
ORDER BY point.id;

-- 4. 輪郭の広さ(km²)。球の上で測った地球での広さを、星と地球の半径の比の二乗で伸び縮みさせる
SELECT area.id, area.name,
       round((ST_Area(area.outline::geography, false) / 1e6
              * (planet.area::float8 / (4 * pi())) / (6371.0088 ^ 2))::numeric) AS outline_km2,
       area.area
FROM location area
JOIN location planet ON planet.id = area.location_planet
WHERE area.outline IS NOT NULL;
