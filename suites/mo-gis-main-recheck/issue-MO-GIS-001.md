### Is there an existing issue for the same bug?

- [x] I have checked existing issues. The earlier SRID mismatch, antimeridian and ST_SymDifference reports describe different behavior.

### Branch Name

main

### Commit ID

`0a4db0e6a6517e489a333ad9073dfcdc5d26aff4`

### Other Environment Information

- Reverified on 2026-10-13 (Asia/Shanghai), using a freshly built binary from the then-current main HEAD and a fresh, isolated data directory.
- Linux x86_64, Go 1.27.1, CGO enabled; single-process LOG/TN/CN, 4 CPU / 32 GiB environment.
- `git_version()` = `0a4db0e`; protocol version = `8.0.30-MatrixOne-v1.3.0`.
- Binary SHA-256: `03a01846386c9e2d69ece702e174b9889b7dc217bc01d0fdf09f4031e6ecc377`.
- Reference engines: PostgreSQL 18.6 / PostGIS 3.6.4 and MySQL 8.0.46.

### Actual Behavior

`ST_Intersection` returns `POLYGON EMPTY` when two valid polygons share an edge or a corner. Their intersection has zero area but is nonempty. Both reference engines preserve the resulting line or point.

### Steps to Reproduce

```sql
-- Shared edge.
SELECT ST_AsText(ST_Intersection(
  ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',0),
  ST_GeomFromText('POLYGON((1 0,2 0,2 1,1 1,1 0))',0)));

-- Shared corner.
SELECT ST_AsText(ST_Intersection(
  ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',0),
  ST_GeomFromText('POLYGON((1 1,2 1,2 2,1 2,1 1))',0)));
```

| Case | MatrixOne | PostGIS and MySQL |
| --- | --- | --- |
| Shared edge | `POLYGON EMPTY` | `LINESTRING(1 0,1 1)` |
| Shared corner | `POLYGON EMPTY` | `POINT(1 1)` |

The same results occur when the inputs are stored in GEOMETRY columns and evaluated as `ST_Intersection(g,h)`.

### Expected Behavior

Preserve lower-dimensional intersections of supported polygon inputs. A shared edge must return the line intersection, and a shared corner must return the point intersection. An empty area alone does not imply an empty set intersection.

### Additional Information

- Both cases reproduced 3/3 times in each of all three engines on fresh-main verification. The stored-column path reproduced too.
- A positive-area overlap control returned area `0.5` correctly in all engines, 3/3 times.
- Earlier broad differential testing found seven examples in this category on main `f1fc3f944e0835af83115675ea18c950be2c2937`; the new main verification confirms it remains.
- This loses shared boundaries and adjacency information in parcel or boundary analysis. It is a wrong-result report; no panic was observed.
- The [overlay kernel](https://github.com/matrixorigin/matrixone/blob/0a4db0e6a6517e489a333ad9073dfcdc5d26aff4/pkg/geo/overlay.go) computes areal outputs. The [shared-edge unit test](https://github.com/matrixorigin/matrixone/blob/0a4db0e6a6517e489a333ad9073dfcdc5d26aff4/pkg/geo/overlay_test.go#L101) checks intersection area zero, which does not validate whether the SQL result retains the shared line.
