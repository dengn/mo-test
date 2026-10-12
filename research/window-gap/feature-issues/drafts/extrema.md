## Why this is needed

Peak/trough age and time-since-anomaly require the location of a frame extreme, not only MIN/MAX value. First and last occurrence differ when the same extreme repeats; this affects recency features and intervention timing.

## Requested behavior and scope

Support position-of-min/max within the current frame, including earliest and latest ties (imin/iminLast/imax/imaxLast or canonical equivalents). The verified contract is zero-based position within the physical frame; NULL rows occupy positions but cannot win. Standard partition-wide ROW_NUMBER or RANK is not an equivalent sliding-frame position. Value-at-extreme is addressed through the max_by OVER request; ordinary max_by already exists.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,imaxLast(v) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, 1, 2, 2, 1, 0**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `imin` | rejected 3/3 | NULL, 1, 1, 0, 0, 2 |
| `imin_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `iminLast` | rejected 3/3 | NULL, 1, 1, 0, 1, 2 |
| `iminLast_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `imax` | rejected 3/3 | NULL, 1, 2, 1, 0, 0 |
| `imax_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `imaxLast` | rejected 3/3 | NULL, 1, 2, 2, 1, 0 |
| `imaxLast_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

Independent NumPy/SciPy checks define the declared mathematical profiles. A separate complete ten-row MO SQL rewrite also recomputed all 17 missing DolphinDB SQL primitives and matched every expected value. That verifies those configurations, not every API option or native execution complexity.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html
