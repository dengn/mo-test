## Why this is needed

Rolling active users, distinct devices, unique fraud counterparties and deduplicated observations require exact per-frame membership. GROUP BY loses the original row stream; cumulative distinct counts cannot handle members leaving a bounded frame. Approximate counts are not a replacement when reconciliation or audit requires exactness.

## Requested behavior and scope

Support COUNT/SUM/AVG(DISTINCT ...) OVER with ROWS and RANGE. Ignore NULL according to the aggregate contract and reference-count duplicates when a frame moves. This differs from #9049, which optimizes existing grouped DISTINCT aggregation rather than implementing currently rejected window DISTINCT.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,COUNT(DISTINCT v) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
FROM (
  SELECT 1 id,1 gid,0 tick,CAST(NULL AS DOUBLE) v,CAST(2.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 2 id,1 gid,0 tick,CAST(2.0 AS DOUBLE) v,CAST(4.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 3 id,1 gid,1 tick,CAST(4.0 AS DOUBLE) v,CAST(3.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 4 id,1 gid,3 tick,CAST(4.0 AS DOUBLE) v,CAST(7.0 AS DOUBLE) y,CAST(3.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 5 id,1 gid,3 tick,CAST(NULL AS DOUBLE) v,CAST(5.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 6 id,1 gid,8 tick,CAST(-1.0 AS DOUBLE) v,CAST(8.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,1 flag) fixture ORDER BY id;
```

Actual MO result, reproduced **3/3**:

```text
(20102, 'DISTINCT in window function is not yet implemented')
```

Expected values in `id` order for the declared profile: **0, 1, 2, 2, 1, 2**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `count_distinct` | rejected 3/3 | 0, 1, 2, 2, 1, 2 |
| `sum_distinct` | rejected 3/3 | NULL, 2, 6, 6, 4, 3 |
| `avg_distinct` | rejected 3/3 | NULL, 2, 3, 3, 4, 1.5 |

DuckDB executed the equivalent window semantics and supplied the full expected output. The postfix IGNORE NULLS spelling is adapted to DuckDB's argument-level spelling without changing the requested semantics.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://duckdb.org/docs/stable/sql/functions/window_functions.html
