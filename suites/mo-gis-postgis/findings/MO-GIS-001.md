# ST_Intersection loses line and point intersections between valid polygons

Reproduced on main `f1fc3f944e0835af83115675ea18c950be2c2937`.

```sql
SELECT ST_AsText(ST_Intersection(
  ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))'),
  ST_GeomFromText('POLYGON((1 0,2 0,2 1,1 1,1 0))')));
```

MatrixOne returns `POLYGON EMPTY`. PostgreSQL 18.6/PostGIS 3.6.4 and MySQL 8.0.46 return `LINESTRING(1 0,1 1)`. When the second polygon is `POLYGON((1 1,2 1,2 2,1 2,1 1))`, MatrixOne also returns `POLYGON EMPTY`, whereas PostGIS returns `POINT(1 1)`.

All inputs are valid, supported polygon types at SRID 0. Their intersection is nonempty even though its area is zero. This loses shared boundaries and corner intersections in adjacency or boundary analysis. Seven generated cases exhibited this behavior; both minimal queries reproduced three times after server recovery. See `boundary-intersection-controls.json`, `minimal-findings.json`, and `findings-repeatability.json`.

Draft only; no issue was created by this suite.
