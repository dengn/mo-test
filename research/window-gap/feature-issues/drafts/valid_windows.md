## Why this is needed

The last two valid measurements should not shrink to one measurement when a missing row arrives. Session boundaries, regime changes and explicit resets also need cumulative state restarted at a predicate boundary without changing event alignment.

## Requested behavior and scope

Provide documented valid-observation-count windows and boundary/reset-aware cumulative operators or migration equivalents. The verified last-two-valid SUM carries 8 across a NULL row, whereas two physical rows would not. A separate verified reset-on-flag SUM profile preserves all input rows. SQL joins and staged windows can calculate these profiles; the requested gap is dedicated declarative/API support and explicit state semantics, not inability to compute them. INTERVAL/SLIDING/FILL already work in MO and are not reported missing.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT movingWindowIndex(CAST(1 AS DOUBLE),3) result;
```

Actual MO result, reproduced **3/3**:

```text
(20105, "not supported: function or operator 'movingwindowindex'")
```

This probe checks **entry-name availability only**. A rejection does not establish that the business calculation is impossible or that this is a valid DolphinDB script signature. The requested mathematical operation is defined above and checked by the independent profile below.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `movingWindowIndex_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `dynamicGroupCumsum_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `dynamicGroupCumcount_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH raw AS (SELECT *
FROM (
  SELECT result id,1 gid,CASE result WHEN 1 THEN 0 WHEN 2 THEN 0 WHEN 3 THEN 1 WHEN 4 THEN 3 WHEN 5 THEN 3 ELSE 8 END tick,CAST(CASE result WHEN 2 THEN 2 WHEN 3 THEN 4 WHEN 4 THEN 4 WHEN 6 THEN -1 ELSE NULL END AS DOUBLE) v,CAST(CASE result WHEN 1 THEN 2 WHEN 2 THEN 4 WHEN 3 THEN 3 WHEN 4 THEN 7 WHEN 5 THEN 5 ELSE 8 END AS DOUBLE) y,CAST(CASE result WHEN 2 THEN 2 WHEN 4 THEN 3 WHEN 6 THEN 2 ELSE 1 END AS DOUBLE) w,CASE result WHEN 2 THEN 0 WHEN 5 THEN 0 ELSE 1 END flag FROM generate_series(1,6) g) fixture),valid_rows AS (SELECT id,v,ROW_NUMBER() OVER(ORDER BY id) ordinal FROM raw WHERE v IS NOT NULL),anchors AS (SELECT a.id,MAX(b.ordinal) current_valid FROM raw a LEFT JOIN valid_rows b ON b.id<=a.id GROUP BY a.id) SELECT a.id,SUM(b.v) result FROM anchors a LEFT JOIN valid_rows b ON b.ordinal BETWEEN a.current_valid-1 AND a.current_valid GROUP BY a.id ORDER BY a.id;
```

| Control | Verified values |
|---|---|
| `last_two_valid_observations_control` | NULL, 2, 6, 8, 8, 3 |
| `reset_on_flag_cumulative_sum_control` | NULL, 2, 4, 4, 4, -1 |

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Functions/Templates/movingvalid.html
