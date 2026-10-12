## Why this is needed

An anomaly baseline should sometimes exclude the observation being evaluated. Peer-excluded benchmarks should exclude concurrent observations at the same timestamp so a burst does not contaminate its own reference. Subtracting the current value from SUM does not generally emulate AVG, variance, non-additive aggregates or NULL frames.

## Requested behavior and scope

Support EXCLUDE CURRENT ROW, GROUP, TIES and NO OTHERS independently of frame membership. Test explicit RANGE peer frames, all-NULL/empty results, duplicate ordering keys and subsequent query usability. This is a SQL extension request: the tested ClickHouse also rejects EXCLUDE, so it is not a claimed ClickHouse-only gap.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,SUM(v) OVER(PARTITION BY gid ORDER BY tick RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW EXCLUDE CURRENT ROW) result
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
(1064, 'SQL parser error: You have an error in your SQL syntax; check the manual that corresponds to your MatrixOne server version for the right syntax to use. syntax error at line
```

Expected values in `id` order for the declared profile: **2, NULL, 2, 6, 10, 10**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `exclude_current_row` | rejected 3/3 | 2, NULL, 2, 6, 10, 10 |
| `exclude_group` | rejected 3/3 | NULL, NULL, 2, 6, 6, 10 |
| `exclude_ties` | rejected 3/3 | NULL, 2, 6, 10, 6, 9 |
| `exclude_no_others` | rejected 3/3 | 2, 2, 6, 10, 10, 9 |

DuckDB executed the equivalent window semantics and supplied the full expected output. The postfix IGNORE NULLS spelling is adapted to DuckDB's argument-level spelling without changing the requested semantics.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://duckdb.org/docs/stable/sql/functions/window_functions.html
