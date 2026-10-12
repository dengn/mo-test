# MatrixOne GIS support: source and runtime verification

MatrixOne has native GIS column types. This check inspected current `main` at
`080365f0134798026fadf162e01e1a78d56be09d`, the `v4.2.5` release source, and
ran SQL against the existing `main` build at
`2726fb419b3afa1db2686ae1b2aaca563d1ae214`.

The runtime probe completed **106 statements: 97 successful checks and 9
expected rejections, with no unexplained failures**. The 18 type/alias forms
each passed CREATE, INSERT, SELECT and SHOW CREATE.

| Area | Verified behavior |
|---|---|
| Generic native type | `GEOMETRY` |
| Subtypes | `POINT`, `LINESTRING`, `POLYGON`, `MULTIPOINT`, `MULTILINESTRING`, `MULTIPOLYGON`, `GEOMETRYCOLLECTION` |
| Float32 family | `GEOMETRY32` and all seven subtype names with a `32` suffix |
| Geography aliases | `GEOGRAPHY` / `GEOGRAPHY32`, generic geometry with SRID 4326 |
| Storage | WKB in the native variable-length value; point payload 21 bytes for float64, 13 for float32 |
| Standard WKB output | `ST_AsBinary` of a float32 point emits standard 21-byte float64 WKB |
| I/O | WKT, WKB and GeoJSON round trips |
| Cartesian math | `(0,0)` to `(3,4)` distance 5; square area 4; line length 5 |
| Geodetic math | SRID 4326 distance `(0,0)` to `(1,0)` = 111195.0802335329 meters |
| Constraints | A LINESTRING insert into POINT is rejected; incompatible SRID is rejected |
| Spatial index | Standalone `CREATE SPATIAL INDEX`; EXPLAIN shows `Index Table Scan`; INSERT/UPDATE/DELETE preserve predicate results |

## Working example

```sql
CREATE TABLE places (id INT PRIMARY KEY, location POINT SRID 4326);
INSERT INTO places VALUES
  (1, ST_GeomFromText('POINT(116.397 39.908)', 4326));
SELECT ST_AsText(location), ST_SRID(location) FROM places;
```

For planar indexing, use:

```sql
CREATE TABLE planar_places (id INT PRIMARY KEY, location POINT NOT NULL);
CREATE SPATIAL INDEX location_idx ON planar_places(location);
```

## Limits and documentation discrepancies

- Spatial computation supports SRID **0 and 4326**. A column may persist another
  SRID such as 3857, but the tested distance operation rejects that SRID.
- `ST_Transform` is not implemented in the tested build. Z/M coordinate types
  are outside the current design; the POINT Z probe is rejected.
- Geometry columns cannot be primary keys or unique-index keys.
- `POINT SRID 4326` works. The design document's
  `GEOMETRY('point',4326)` and `GEOMETRY(type='point',srid=4326)` forms are
  rejected by the runtime parser. The current-main grammar also contains only
  bare spatial type names, rather than these parameter forms.
- Use standalone `CREATE SPATIAL INDEX`. The initially attempted inline
  `SPATIAL INDEX` spelling failed to parse; SHOW CREATE emits `SPATIAL KEY`.
- The planner deliberately skips the spatial index for SRID 4326 and retains
  the precise predicate on the base table: current index envelopes cannot safely
  represent longitude intervals crossing the antimeridian. This behavior was
  inspected in source; the runtime index test used SRID 0.

The source contains additional functions (overlay, buffer, geohash, etc.) and
many GIS BVT files. This smoke check does not claim full testing of every
registered spatial function, scale/performance behavior, or PostGIS parity.

## Sources and artifacts

- [Native types on observed main](https://github.com/matrixorigin/matrixone/blob/080365f0134798026fadf162e01e1a78d56be09d/pkg/container/types/types.go)
- [Types in v4.2.5](https://github.com/matrixorigin/matrixone/blob/v4.2.5/pkg/container/types/types.go)
- [GIS engine constants and supported SRIDs](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/pkg/geo/consts.go)
- [Spatial index selection and geodetic fallback](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/pkg/sql/plan/apply_indices.go#L341)
- [GIS BVT coverage](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/test/distributed/cases/geo/README.md)
- `check.py`, `results.json`, `summary.json`: verified smoke run.
- `calibration-*`: original discovery run, retaining failed design syntax and
  dependent missing-table errors. These are not counted as distinct bugs.

Run `python check.py` with PyMySQL installed. It defaults to a fresh database
name; set `MO_GIS_TEST_DATABASE` to select an unused database explicitly.
