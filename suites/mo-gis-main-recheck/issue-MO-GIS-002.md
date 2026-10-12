### Is there an existing issue for the same bug?

- [x] I have checked existing issues.

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

`ST_IsValid` returns 0 for a LineString with adjacent repeated coordinates even though the line contains distinct endpoints and has positive length.

### Steps to Reproduce

```sql
SELECT ST_IsValid(
  ST_GeomFromText('LINESTRING(0 0,0 0,1 0,1 0)',0));

-- Positive control.
SELECT ST_IsValid(ST_GeomFromText('LINESTRING(0 0,1 0)',0));
```

| Input | MatrixOne | PostGIS | MySQL |
| --- | --- | --- | --- |
| Adjacent repeated vertices | `0` | `true` | `1` |
| Line without repetitions | `1` | `true` | `1` |

The same false validity result occurs after storing the repeated-vertex line in a GEOMETRY column and evaluating `ST_IsValid(g)`.

### Expected Behavior

Return true for this structurally valid LineString, consistent with MySQL, PostGIS and independent Shapely validation. Adjacent repeated coordinates alone must not invalidate a line that has two distinct points and nonzero length.

### Additional Information

- The reproducer and positive control each ran 3/3 times in all three engines. The stored-column path reproduced too.
- This was previously found in both constant and stored paths on main `f1fc3f944e0835af83115675ea18c950be2c2937` and persists in fresh-main verification.
- Incorrect invalidity rejects otherwise usable line data during GIS import or quality checks. No panic was observed.
- The current [lineStringIsValidFromPayload](https://github.com/matrixorigin/matrixone/blob/0a4db0e6a6517e489a333ad9073dfcdc5d26aff4/pkg/sql/plan/function/func_unary.go#L5037) returns false whenever two adjacent points are equal.
- This report concerns `ST_IsValid`. A separately observed `ST_IsSimple` difference on the same input follows MySQL behavior and is not included in this report.
