## Why this is needed

Telemetry gaps, sparse prices and intermittent customer events require the previous/next observed value and the first/last valid observation in a frame. Filtering NULL rows upstream changes row counts, timestamps and alignment with other metrics, so it is not a general replacement.

## Requested behavior and scope

Support IGNORE NULLS for FIRST_VALUE, LAST_VALUE, NTH_VALUE, LAG and LEAD while preserving the original rows. Document a mapping for DolphinDB firstNot/lastNot. RESPECT NULLS is already accepted on this tested revision; this request does not reopen the completed #28031. The explicit NULL-default execution bug is separately tracked by #29925.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,LAST_VALUE(v) IGNORE NULLS OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, 2, 4, 4, 4, -1**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `first_value_ignore_nulls` | rejected 3/3 | NULL, 2, 2, 2, 4, 4 |
| `last_value_ignore_nulls` | rejected 3/3 | NULL, 2, 4, 4, 4, -1 |
| `nth_value_ignore_nulls` | rejected 3/3 | NULL, NULL, 4, 4, 4, -1 |
| `lag_ignore_nulls` | rejected 3/3 | NULL, NULL, 2, 4, 4, 4 |
| `lead_ignore_nulls` | rejected 3/3 | 2, 4, 4, -1, -1, NULL |
| `firstNot` | rejected 3/3 | NULL, 2, 2, 2, 4, 4 |
| `lastNot` | rejected 3/3 | NULL, 2, 4, 4, 4, -1 |
| `firstNot_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `lastNot_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

Independent NumPy/SciPy checks define the declared mathematical profiles. A separate complete ten-row MO SQL rewrite also recomputed all 17 missing DolphinDB SQL primitives and matched every expected value. That verifies those configurations, not every API option or native execution complexity.

DuckDB executed the equivalent window semantics and supplied the full expected output. The postfix IGNORE NULLS spelling is adapted to DuckDB's argument-level spelling without changing the requested semantics.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://clickhouse.com/docs/reference/functions/window-functions/last_value
