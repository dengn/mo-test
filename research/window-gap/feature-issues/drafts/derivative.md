## Why this is needed

Network-byte, energy-meter and transaction counters need a rate per unit time. Adjacent observations may be two seconds or minutes apart, so a raw value delta is not a rate. Resets require an explicit policy; the requested profile clamps a negative delta to zero.

## Requested behavior and scope

Provide nonNegativeDerivative or a documented native equivalent using ordered event time and an optional time unit. Define first-row, NULL, duplicate/non-increasing timestamps and reset behavior. The verified profile uses seconds and non-NULL counters, returning 0,3,0 for (10@0s,16@2s,5@5s). This is not the full Prometheus counter-reset extrapolation contract.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,nonNegativeDerivative(counter,stamp) OVER(ORDER BY stamp) result
FROM (
  SELECT 1 id,CAST(10 AS DOUBLE) counter,CAST('2024-01-01 00:00:00' AS DATETIME) stamp
  UNION ALL SELECT 2,CAST(16 AS DOUBLE),CAST('2024-01-01 00:00:02' AS DATETIME)
  UNION ALL SELECT 3,CAST(5 AS DOUBLE),CAST('2024-01-01 00:00:05' AS DATETIME)) fixture ORDER BY id;
```

Actual MO result, reproduced **3/3**:

```text
(1064, 'SQL parser error: You have an error in your SQL syntax; check the manual that corresponds to your MatrixOne server version for the right syntax to use. syntax error at line
```

Expected values in `id` order for the declared profile: **0, 3, 0**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `nonNegativeDerivative` | rejected 3/3 | 0, 3, 0 |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH a AS (SELECT *,LAG(counter) OVER(ORDER BY stamp) prev,LAG(stamp) OVER(ORDER BY stamp) prev_ts
FROM (
  SELECT 1 id,CAST(10 AS DOUBLE) counter,CAST('2024-01-01 00:00:00' AS DATETIME) stamp
  UNION ALL SELECT 2,CAST(16 AS DOUBLE),CAST('2024-01-01 00:00:02' AS DATETIME)
  UNION ALL SELECT 3,CAST(5 AS DOUBLE),CAST('2024-01-01 00:00:05' AS DATETIME)) fixture) SELECT id,CASE WHEN prev IS NULL THEN CAST(0 AS DOUBLE) ELSE GREATEST(CAST(0 AS DOUBLE),(counter-prev)/NULLIF(CAST(TIMESTAMPDIFF(SECOND,prev_ts,stamp) AS DOUBLE),0)) END result FROM a ORDER BY id;
```

| Control | Verified values |
|---|---|
| `delta_time_control` | 0, 3, 0 |

## Live ClickHouse correctness control

ClickHouse 26.9.16.11 executed this explicit SQL and returned the expected result:

```sql
SELECT number+1 id, arrayElement([toFloat64(10),toFloat64(16),toFloat64(5)],number+1) counter, toDateTime('2024-01-01 00:00:00')+toIntervalSecond(arrayElement([0,2,5],number+1)) stamp, nonNegativeDerivative(counter,stamp) OVER(ORDER BY stamp) result FROM numbers(3) ORDER BY id;
```

```json
[
  {
    "id": 1,
    "counter": 10,
    "stamp": "2024-01-01 00:00:00",
    "result": 0
  },
  {
    "id": 2,
    "counter": 16,
    "stamp": "2024-01-01 00:00:02",
    "result": 3
  },
  {
    "id": 3,
    "counter": 5,
    "stamp": "2024-01-01 00:00:05",
    "result": 0
  }
]
```

Reference encoding note: The same three rows are encoded via numbers/arrays in the CH derivative reference; the UNION literal CH shape returned zeros and is not used as a correctness oracle.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://clickhouse.com/docs/reference/functions/window-functions/nonNegativeDerivative
