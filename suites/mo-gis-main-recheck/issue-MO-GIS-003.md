### Is there an existing issue for the same bug?

- [x] I have checked existing issues. The previous invalid ST_SymDifference output report involves different, initially valid input geometries.

### Branch Name

main

### Commit ID

`0a4db0e6a6517e489a333ad9073dfcdc5d26aff4`

### Other Environment Information

- Reverified on 2026-10-13 (Asia/Shanghai), using a freshly built binary from the then-current main HEAD and a fresh, isolated data directory.
- Linux x86_64, Go 1.27.1, CGO enabled; single-process LOG/TN/CN, 4 CPU / 32 GiB environment.
- `git_version()` = `0a4db0e`; protocol version = `8.0.30-MatrixOne-v1.3.0`.
- Binary SHA-256: `03a01846386c9e2d69ece702e174b9889b7dc217bc01d0fdf09f4031e6ecc377`.
- References: PostgreSQL 18.6 / PostGIS 3.6.4, MySQL 8.0.46 and Shapely 2.2.0.

### Actual Behavior

`ST_GeomFromText` accepts an unclosed, three-position polygon ring. The geometry can also be persisted in a GEOMETRY column. `ST_AsGeoJSON` exports the malformed ring, and `ST_AsWKB` emits bytes that an independent geometry reader cannot decode.

### Steps to Reproduce

```sql
SELECT ST_AsText(ST_GeomFromText('POLYGON((0 0,1 0,1 1))',0));
SELECT ST_AsGeoJSON(ST_GeomFromText('POLYGON((0 0,1 0,1 1))',0));
SELECT HEX(ST_AsWKB(ST_GeomFromText('POLYGON((0 0,1 0,1 1))',0)));
```

MatrixOne returns:

```text
WKT: POLYGON((0 0,1 0,1 1))
GeoJSON: {"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1]]]}
WKB hex: 0103000000010000000300000000000000000000000000000000000000000000000000F03F0000000000000000000000000000F03F000000000000F03F
```

PostGIS rejects the constructor with `geometry requires more points`; MySQL rejects it with error 3037, `Invalid GIS data provided to function st_geomfromtext.`

Independent decode of MatrixOne's emitted WKB:

```python
import shapely
shapely.from_wkb(bytes.fromhex(
    '0103000000010000000300000000000000000000000000000000000000000000000000F03F0000000000000000000000000000F03F000000000000F03F'))
# GEOSException:
# IllegalArgumentException: Points of LinearRing do not form a closed linestring
```

### Expected Behavior

Reject structurally malformed polygon rings during WKT construction/admission, consistent with the MySQL-compatible constructor. A polygon linear ring must be closed and have at least four positions including the closing position. Successfully exported WKB/GeoJSON must be structurally usable by conforming consumers.

### Additional Information

- All three constructor/export queries reproduced 3/3 times in MatrixOne; both reference engines rejected every corresponding query. Each emitted WKB independently failed decoding.
- The stored-column path also accepts this value and emits the same unclosed GeoJSON ring.
- Valid closed-ring construction and validity controls passed in all three engines.
- This remains on fresh main after the earlier observation on `f1fc3f944e0835af83115675ea18c950be2c2937`.
- This is a structural admission/interoperability issue, not simply a topologically self-intersecting polygon. No panic was observed.
- Relevant entry: [WKT parsePolygon](https://github.com/matrixorigin/matrixone/blob/0a4db0e6a6517e489a333ad9073dfcdc5d26aff4/pkg/geo/wkt_parse.go#L100).
