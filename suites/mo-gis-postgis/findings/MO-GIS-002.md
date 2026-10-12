# ST_IsValid rejects a valid LineString with adjacent repeated vertices

Reproduced on main `f1fc3f944e0835af83115675ea18c950be2c2937`.

```sql
SELECT ST_IsValid(ST_GeomFromText('LINESTRING(0 0,0 0,1 0,1 0)'));
```

MatrixOne returns 0. PostGIS 3.6.4 returns true, MySQL 8.0.46 returns 1, and Shapely 2.2.0 reports a valid geometry. The line has two distinct endpoints and positive length; adjacent repeated coordinates do not make it structurally invalid.

Both stored-column and constant paths reproduce; the minimal query reproduced three times after recovery. Incorrect validity rejects otherwise usable imported line data. This finding concerns `ST_IsValid`; the separately observed `ST_IsSimple` difference for the same input follows MySQL behavior and is not included in this finding. Evidence: `validity-and-ring-controls.json`, `mysql-semantic-controls.json`, `findings-repeatability.json`.

Draft only; no issue was created by this suite.
