# WKT constructor accepts an unclosed polygon ring and exports unreadable WKB

Reproduced on main `f1fc3f944e0835af83115675ea18c950be2c2937`.

```sql
SELECT ST_AsText(ST_GeomFromText('POLYGON((0 0,1 0,1 1))'));
SELECT ST_AsGeoJSON(ST_GeomFromText('POLYGON((0 0,1 0,1 1))'));
SELECT HEX(ST_AsWKB(ST_GeomFromText('POLYGON((0 0,1 0,1 1))')));
```

MatrixOne accepts the input and preserves its unclosed three-coordinate ring. PostGIS 3.6.4 rejects it because the ring requires more points; MySQL 8.0.46 rejects the invalid GIS input (3037).

The GeoJSON ring is unclosed and has fewer than the required four positions. Shapely cannot decode the emitted WKB and raises `IllegalArgumentException: Points of LinearRing do not form a closed linestring`. Constructor admission should reject this malformed structure or follow a documented normalization policy that produces a valid closed ring; exporting an unreadable geometry breaks interoperation. Evidence: `validity-and-ring-controls.json`, `minimal-findings.json`, `findings-repeatability.json`.

Reverified on main `0a4db0e6a6517e489a333ad9073dfcdc5d26aff4` and submitted as [30034](https://github.com/matrixorigin/matrixone/issues/30034) on 2026-10-13 (Asia/Shanghai). See the latest-main recheck suite for current evidence and full issue body.
