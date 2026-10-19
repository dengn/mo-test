## Why this is needed

An alert often asks how unusual the current observation is relative to the most recent observations. Partition-wide rank changes with the entire history and does not answer that local question; assigning a ROWS clause to RANK does not make it frame-local.

## Requested behavior and scope

Provide moving/time/cumulative local-rank operators or a canonical SQL equivalent with documented competition/dense/average/percentile conventions and direction. The verified business profile is 1-based ascending competition rank of the current non-NULL value in the last three physical rows, returning NULL when the current value is NULL. This is a declared profile, not an assertion about all DolphinDB default rank conventions.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT mrank(CAST(1 AS DOUBLE),3) result;
```

Actual MO result, reproduced **3/3**:

```text
(20105, "not supported: function or operator 'mrank'")
```

This probe checks **entry-name availability only**. A rejection does not establish that the business calculation is impossible or that this is a valid DolphinDB script signature. The requested mathematical operation is defined above and checked by the independent profile below.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `mrank_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `tmrank_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `cumrank_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH raw AS (SELECT *
FROM (
  SELECT 1 id,1 gid,0 tick,CAST(NULL AS DOUBLE) v,CAST(2.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 2 id,1 gid,0 tick,CAST(2.0 AS DOUBLE) v,CAST(4.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 3 id,1 gid,1 tick,CAST(4.0 AS DOUBLE) v,CAST(3.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 4 id,1 gid,3 tick,CAST(4.0 AS DOUBLE) v,CAST(7.0 AS DOUBLE) y,CAST(3.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 5 id,1 gid,3 tick,CAST(NULL AS DOUBLE) v,CAST(5.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 6 id,1 gid,8 tick,CAST(-1.0 AS DOUBLE) v,CAST(8.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,1 flag) fixture) SELECT a.id,CASE WHEN a.v IS NULL THEN NULL ELSE 1+SUM(CASE WHEN b.v<a.v THEN 1 ELSE 0 END) END result FROM raw a JOIN raw b ON b.id BETWEEN a.id-2 AND a.id GROUP BY a.id,a.v ORDER BY a.id;
```

| Control | Verified values |
|---|---|
| `local_competition_rank_control` | NULL, 1, 2, 2, NULL, 1 |

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Functions/Themes/mFunctions.html
