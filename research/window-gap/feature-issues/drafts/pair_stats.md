## Why this is needed

Rolling sensor correlation, asset co-movement and multi-signal drift detection need paired statistics. Independent NULL filtering for x and y is wrong: every moment must use the same eligible pairs. Hand-written subtraction of large raw moments can also be numerically unstable.

## Requested behavior and scope

Add CORR and population/sample covariance with documented aliases such as covar/COVAR_SAMP/COVAR_POP and bounded-window support. Test paired NULLs, minimum observations and zero variance. This fixture uses sample covariance and Pearson correlation. Linear-regression slope/intercept are already requested by #10182; fresh slope/REGR cases are being added there rather than filing another regression issue.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,corr(v,y) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, NULL, -1, 0.2773500981, NULL, -1**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `corr` | rejected 3/3 | NULL, NULL, -1, 0.2773500981, NULL, -1 |
| `corr_entry` | rejected 3/3 | Entry resolution only; no invented engine result |
| `covar` | rejected 3/3 | NULL, NULL, -1, 0.6666666667, 0, -2.5 |
| `covar_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

Independent NumPy/SciPy checks define the declared mathematical profiles. A separate complete ten-row MO SQL rewrite also recomputed all 17 missing DolphinDB SQL primitives and matched every expected value. That verifies those configurations, not every API option or native execution complexity.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html
