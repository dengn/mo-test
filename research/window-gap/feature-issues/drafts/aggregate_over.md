## Why this is needed

Analysts need the payload belonging to a rolling maximum key, a deterministic latest/earliest observation and representative attributes alongside window metrics. MAX(payload) does not select the payload at MAX(key). Ordinary aggregation cannot preserve one output per event.

## Requested behavior and scope

Extend supported registered aggregates max_by(value,key,tie) and any_value(value) to OVER. max_by(value,-key,-id) expresses the earliest minimum-key payload for this numeric fixture, covering the value-at-extreme use case of atImax/atImin. Preserve explicit tie and NULL contracts; ANY_VALUE may return any allowed frame member. Both functions already execute as ordinary aggregates. #27064 is a completed tumbling-Time-Window arity bug; this request concerns currently rejected ordinary OVER composition.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,max_by(v,y,-id) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, 2, 2, 4, 4, -1**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `max_by_over` | rejected 3/3 | NULL, 2, 2, 4, 4, -1 |
| `any_value_over` | rejected 3/3 | Entry resolution only; no invented engine result |
| `max_by_min_key_over` | rejected 3/3 | NULL, NULL, NULL, 4, 4, NULL |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
SELECT max_by(v,y,-id) result
FROM (
  SELECT 1 id,1 gid,0 tick,CAST(NULL AS DOUBLE) v,CAST(2.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 2 id,1 gid,0 tick,CAST(2.0 AS DOUBLE) v,CAST(4.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 3 id,1 gid,1 tick,CAST(4.0 AS DOUBLE) v,CAST(3.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 4 id,1 gid,3 tick,CAST(4.0 AS DOUBLE) v,CAST(7.0 AS DOUBLE) y,CAST(3.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 5 id,1 gid,3 tick,CAST(NULL AS DOUBLE) v,CAST(5.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 6 id,1 gid,8 tick,CAST(-1.0 AS DOUBLE) v,CAST(8.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,1 flag) fixture;
```

| Control | Verified values |
|---|---|
| `max_by_aggregate_control` | -1 |
| `any_value_aggregate_control` | -1 |
| `max_by_tie_control` | 9 |

`ANY_VALUE` has no deterministic winner contract; the observed value was an allowed member of this fixture. The max_by tie control returns oldest/latest payloads 2 and 9 for equal keys. Ordinary aggregation is already supported; OVER composition is the rejected part.

Independent NumPy/SciPy checks define the declared mathematical profiles. A separate complete ten-row MO SQL rewrite also recomputed all 17 missing DolphinDB SQL primitives and matched every expected value. That verifies those configurations, not every API option or native execution complexity.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.matrixorigin.cn/mo/zh/latest/MatrixOne/Develop/read-data/window-function/time-window.html
