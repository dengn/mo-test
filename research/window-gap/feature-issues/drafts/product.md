## Why this is needed

Compounded growth factors, survival probabilities and multiplicative scores require products over a bounded or cumulative window. SUM is not interchangeable with multiplication; a naive EXP(SUM(LN(x))) fails for zero and negative factors.

## Requested behavior and scope

Add a product aggregate with explicit NULL/empty, zero, sign, overflow/underflow and numeric-type contracts. The verified common profile skips NULL, returns NULL for an all-NULL frame, preserves negative signs and returns zero when a zero factor is present. A guarded SQL expression works on the tested fixtures; native implementation should be checked against those full outputs.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,prod(v) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, 2, 8, 32, 16, -4**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `prod` | rejected 3/3 | NULL, 2, 8, 32, 16, -4 |
| `prod_entry` | rejected 3/3 | Entry resolution only; no invented engine result |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
WITH a AS (SELECT id,COUNT(v) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) n,SUM(CASE WHEN v=0 THEN 1 ELSE 0 END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) z,SUM(CASE WHEN v<0 THEN 1 ELSE 0 END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) neg,SUM(CASE WHEN v IS NOT NULL AND v<>0 THEN LN(ABS(v)) ELSE CAST(0 AS DOUBLE) END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) lp
FROM (
  SELECT 1 id,CAST(-2 AS DOUBLE) v
  UNION ALL SELECT 2,0
  UNION ALL SELECT 3,3) f) SELECT id,CASE WHEN n=0 THEN NULL WHEN z>0 THEN CAST(0 AS DOUBLE) ELSE EXP(lp)*CASE WHEN MOD(neg,2)=0 THEN 1 ELSE -1 END END result FROM a ORDER BY id;
```

| Control | Verified values |
|---|---|
| `zero_and_negative_product_control` | -2, 0, 0 |

Independent NumPy/SciPy checks define the declared mathematical profiles. A separate complete ten-row MO SQL rewrite also recomputed all 17 missing DolphinDB SQL primitives and matched every expected value. That verifies those configurations, not every API option or native execution complexity.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html
