## Why this is needed

Trades, device readings and batch events often share a timestamp. Analysts need the previous K distinct timestamps or price levels, including every peer, rather than K physical rows or a fixed elapsed-time distance. ROWS can split peers; RANGE cannot express a count of peer groups.

## Requested behavior and scope

Implement GROUPS frame bounds with correct peer equality, partition boundaries and inclusive endpoints. In this test ORDER BY tick deliberately omits id so equal ticks form peers.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,SUM(v) OVER(PARTITION BY gid ORDER BY tick GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) result
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
(20102, 'GROUPS in WINDOW FUNCTION condition is not yet implemented')
```

Expected values in `id` order for the declared profile: **2, 2, 6, 8, 8, 3**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `groups` | rejected 3/3 | 2, 2, 6, 8, 8, 3 |

DuckDB executed the equivalent window semantics and supplied the full expected output. The postfix IGNORE NULLS spelling is adapted to DuckDB's argument-level spelling without changing the requested semantics.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://clickhouse.com/docs/reference/functions/window-functions
