## Why this is needed

Financial/risk and telemetry workflows commonly use smoothed indicators, drawdown, streaks and local trends. Each library has seeding, warmup and missing-data conventions; repeatedly porting formulas increases maintenance and validation cost.

## Requested behavior and scope

Add documented SQL/migration equivalents for the missing EMA/DEMA/TEMA/T3/KAMA/Wilder/WMA/SMA/TRIMA family and rolling drawdown/streak/trend operators. Prioritize well-defined profiles with warmup and NULL semantics rather than claiming all TA-Lib defaults are identical. The verified price fixture 100,120,90,110 has cumulative maximum drawdown ratios 0,0,0.25,0.25 using ordinary SQL windows. Bounded-frame drawdown must use frame-local peaks, not the all-history peak. No live DolphinDB/TA-Lib performance comparison is claimed.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT mmaxDrawdown(CAST(1 AS DOUBLE),3) result;
```

Actual MO result, reproduced **3/3**:

```text
(20105, "not supported: function or operator 'mmaxdrawdown'")
```

This probe checks **entry-name availability only**. A rejection does not establish that the business calculation is impossible or that this is a valid DolphinDB script signature. The requested mathematical operation is defined above and checked by the independent profile below.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `ema_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `kama_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `mmaxDrawdown_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `cumPositiveStreak_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH a AS (SELECT id,price,MAX(price) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) peak
FROM (
  SELECT 1 id,CAST(100 AS DOUBLE) price
  UNION ALL SELECT 2,120
  UNION ALL SELECT 3,90
  UNION ALL SELECT 4,110) fixture) SELECT id,MAX(CAST(1 AS DOUBLE)-price/peak) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) result FROM a ORDER BY id;
```

| Control | Verified values |
|---|---|
| `cumulative_max_drawdown_control` | 0, 0, 0.25, 0.25 |

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Functions/Themes/TALib.html
