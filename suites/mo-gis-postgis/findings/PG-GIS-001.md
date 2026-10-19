# PostGIS 3.6.4 geography spherical area appears to retain WGS84 flattening

Reference-side finding, independent of MatrixOne correctness. Environment: PostgreSQL 18.6, PostGIS 3.6.4 94d984b, PROJ 9.8.1.

```sql
SELECT ST_Area(ST_GeomFromText(
 'POLYGON((0 0,1 0,1 1,0 1,0 0))',4326)::geography,false);
```

Actual: `12281281066.690842` m². An independent equal-axes sphere with mean radius 6371008.8 gives `12364031909.465616` m². MatrixOne's spherical result matches the latter.

Three latitude ranges reproduce. Recalculating with mean radius 6371008.77141506 while retaining WGS84 flattening `1/298.257223563` gives `12281281066.690844` m² for the first polygon and matches the other two anomalous outputs within tiny rounding error. Ellipsoidal `ST_Area(...,true)` matches independent WGS84 correctly.

In tag 3.6.4, geography_area changes `s.a = s.b = s.radius` for `use_spheroid=false`, then calls `lwgeom_area_spheroid`. Under the PROJ geodesic path, `ptarray_area_spheroid` uses `geod_init(&gd, spheroid->a, spheroid->f)`, retaining the original flattening. Source snapshots and numerical controls are included. This supports a stale-flattening diagnosis for this build; it does not establish the scope across other versions or build configurations.

Evidence: `geodetic-area-controls.json`, `postgis-stale-flattening-controls.json`, `sources/postgis-geography_measurement.c`, `sources/postgis-lwspheroid.c`.

Draft only; no external PostGIS issue was created.
