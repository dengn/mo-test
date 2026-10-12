## Why this is needed

Online anomaly baselines and adaptive volatility need gradual forgetting rather than a hard cutoff. Irregular event-time decay and missing samples require explicit half-life/ignoreNA behavior; a fixed ROWS average is not equivalent.

## Requested behavior and scope

Provide exponentially weighted mean/variance/std/covariance/correlation with declared alpha/com/span/half-life, adjust, ignoreNA and initialization policies. The verified simple profile is alpha=0.5, adjust=False, no missing samples, first-sample initialization: values 1,2,3,4 produce means 1,1.5,2.25,3.125. A finite historical self-join can emulate that profile, but does not establish a native incremental-state API or performance parity.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT ewmMean(CAST(1 AS DOUBLE),3) result;
```

Actual MO result, reproduced **3/3**:

```text
(20105, "not supported: function or operator 'ewmmean'")
```

This probe checks **entry-name availability only**. A rejection does not establish that the business calculation is impossible or that this is a valid DolphinDB script signature. The requested mathematical operation is defined above and checked by the independent profile below.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `ewmMean_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `ewmVar_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `ewmStd_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `ewmCov_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `ewmCorr_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH raw AS (SELECT *
FROM (
  SELECT 1 id,CAST(1 AS DOUBLE) v
  UNION ALL SELECT 2,2
  UNION ALL SELECT 3,3
  UNION ALL SELECT 4,4) fixture) SELECT a.id,SUM(b.v*CASE WHEN b.id=1 THEN POWER(CAST(0.5 AS DOUBLE),a.id-1) ELSE CAST(0.5 AS DOUBLE)*POWER(CAST(0.5 AS DOUBLE),a.id-b.id) END) result FROM raw a JOIN raw b ON b.id<=a.id GROUP BY a.id ORDER BY a.id;
```

| Control | Verified values |
|---|---|
| `alpha_half_adjust_false_control` | 1, 1.5, 2.25, 3.125 |

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Functions/e/ewmMean.html
