## Problem

A direct `SELECT` of a GEOMETRY column is advertised with MySQL field type 255 (`MYSQL_TYPE_GEOMETRY`), but MatrixOne sends ASCII WKT as the value. MySQL-compatible GIS clients expect the binary MySQL geometry representation: a four-byte little-endian SRID followed by WKB.

Consequently, the GDAL MySQL driver opens the table and returns attributes/features, but every tested feature has a null geometry. QGIS's native MySQL/OGR connection exhibits the same failure. This blocks direct GIS application access even though explicit `ST_AsWKB()` returns correct WKB.

## Environment

- MatrixOne built from main commit `fa7cc1d9b38e3324572a4efc5617033522de0cbf`; runtime `git_version()` = `fa7cc1d9`.
- Later observed main `3e50e1b32d8da61bbbf70c89989fb08b671809de` has identical `pkg/frontend/output.go` and `pkg/frontend/mysql_protocol.go`; no runtime rebuild of that later commit is claimed.
- Reference: MySQL 8.0.46.
- GDAL 3.10; QGIS 3.40.6; PyMySQL raw bytes.
- SRID 0 is used to eliminate EPSG:4326 axis-order differences from the reproduction.

## Reproduction

Run on MatrixOne and MySQL:

```sql
CREATE TABLE wire_geometry_repro (id INT PRIMARY KEY, geom GEOMETRY);
INSERT INTO wire_geometry_repro VALUES (1, ST_GeomFromText('POINT(116.3 39.8)', 0));
SELECT geom, ST_AsWKB(geom), ST_SRID(geom) FROM wire_geometry_repro;
```

Inspect the first selected column using a MySQL client library without geometry conversion:

```python
with connection.cursor() as cursor:
    cursor.execute('SELECT geom FROM wire_geometry_repro WHERE id=1')
    value = cursor.fetchone()[0]
    print(cursor.description[0][1], len(value), value.hex())
```

Observed:

| Server | Field type | Value bytes | Hex |
|---|---:|---:|---|
| MySQL | 255 | 25 | `0000000001010000003333333333135d406666666666e64340` |
| MatrixOne | 255 | 17 | `504f494e54283131362e332033392e3829` |

MatrixOne's bytes decode to `POINT(116.3 39.8)`. On both engines `ST_AsWKB()` returns `01010000003333333333135d406666666666e64340`, and `ST_SRID()` returns 0.

Use the real GDAL MySQL driver, replacing credentials/port with the local instance:

```python
from osgeo import ogr
dataset = ogr.Open('MYSQL:test_db,host=127.0.0.1,port=6001,user=root,password=LOCAL_PASSWORD')
layer = dataset.GetLayerByName('wire_geometry_repro')
feature = layer.GetNextFeature()
print(feature.GetGeometryRef())
```

Expected: a POINT geometry, as on MySQL. Actual on MatrixOne: `None`, despite the non-null source geometry. In the larger identical fixture, three GDAL features returned their expected POINT geometries on MySQL and three returned null geometry on MatrixOne. QGIS saw 259 rows but no usable native geometries.

## Source evidence and impact

`pkg/frontend/output.go` converts `types.T_geometry`/`T_geometry32` with `GeometryPayloadToText()` and places `[]byte(text)` in the result row (e.g. around line 94). Geometry result metadata/protocol handling still uses `MYSQL_TYPE_GEOMETRY`. Text rendering appropriate for display is therefore exposed as incompatible wire data for a typed geometry column.

Please return a representation consistent with the advertised MySQL geometry type, including SRID/WKB, and cover both result protocol paths. Explicit `ST_AsWKB()` plus an application adapter or a GeoServer/OGC API intermediary is a workaround; it does not repair native MySQL-driver access.

No MatrixOne panic was observed in this reproduction. The initial headless QGIS teardown crash in the test harness was separately corrected and is not evidence of a database panic.
