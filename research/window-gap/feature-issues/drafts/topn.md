## Why this is needed

Risk and operational dashboards need averages, sums, covariance or percentiles of the highest-N exposures or most severe observations inside a rolling frame. A partition-wide TOP/LIMIT or ROW_NUMBER is not the same as selecting TopN separately for every moving frame.

## Requested behavior and scope

Provide frame-local TopN selection and aggregate families (m/tm/cum TopN equivalents), explicit selection key, N, direction and oldest/latest/all tie policy. The verified profile averages the top two eligible values by descending y in the last three physical rows, breaking ties by oldest id; NULL payloads are excluded before selection. A self-join + per-anchor ROW_NUMBER rewrite computes this profile but expands frame members. Define minPeriods and oversized-N behavior; no cross-database performance result is claimed.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT mavgTopN(CAST(1 AS DOUBLE),3) result;
```

Actual MO result, reproduced **3/3**:

```text
(20105, "not supported: function or operator 'mavgtopn'")
```

This probe checks **entry-name availability only**. A rejection does not establish that the business calculation is impossible or that this is a valid DolphinDB script signature. The requested mathematical operation is defined above and checked by the independent profile below.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `mavgTopN_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `tmavgTopN_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `cumavgTopN_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `movingTopNIndex_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH raw AS (SELECT *
FROM (
  SELECT result id,1 gid,CASE result WHEN 1 THEN 0 WHEN 2 THEN 0 WHEN 3 THEN 1 WHEN 4 THEN 3 WHEN 5 THEN 3 ELSE 8 END tick,CAST(CASE result WHEN 2 THEN 2 WHEN 3 THEN 4 WHEN 4 THEN 4 WHEN 6 THEN -1 ELSE NULL END AS DOUBLE) v,CAST(CASE result WHEN 1 THEN 2 WHEN 2 THEN 4 WHEN 3 THEN 3 WHEN 4 THEN 7 WHEN 5 THEN 5 ELSE 8 END AS DOUBLE) y,CAST(CASE result WHEN 2 THEN 2 WHEN 4 THEN 3 WHEN 6 THEN 2 ELSE 1 END AS DOUBLE) w,CASE result WHEN 2 THEN 0 WHEN 5 THEN 0 ELSE 1 END flag FROM generate_series(1,6) g) fixture),members AS (SELECT a.id,b.v,ROW_NUMBER() OVER(PARTITION BY a.id ORDER BY b.y DESC,b.id ASC) position FROM raw a JOIN raw b ON b.id BETWEEN a.id-2 AND a.id AND b.v IS NOT NULL),chosen AS (SELECT id,AVG(v) result FROM members WHERE position<=2 GROUP BY id) SELECT a.id,b.result FROM raw a LEFT JOIN chosen b ON a.id=b.id ORDER BY a.id;
```

| Control | Verified values |
|---|---|
| `top_two_by_key_average_control` | NULL, 2, 3, 3, 4, 1.5 |

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Functions/Themes/mTopN.html
