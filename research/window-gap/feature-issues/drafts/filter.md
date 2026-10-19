## Why this is needed

A dashboard often computes successful orders, failures and valid samples over the same time frame. FILTER expresses eligibility per metric without deleting rows needed by other metrics and improves portability of PostgreSQL/DuckDB-generated analytical SQL.

## Requested behavior and scope

Accept aggregate FILTER(WHERE predicate), including its composition with OVER. COUNT(*) and SUM have different NULL/empty-frame behavior, which must be retained. SUM(CASE WHEN ... THEN value ELSE NULL END) is already a working alternative on the test fixture; this is a syntax/composability request, not a claim the math is impossible.

## Tested revision / existing issue check

- MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.
- Existing issues were searched before filing; related requests/closed fixes are distinguished above.
- All data below is synthetic. The probe is read-only and requires no persisted tables.

## Executable unsupported case

```sql
SELECT id,SUM(v) FILTER(WHERE flag=1) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
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

Expected values in `id` order for the declared profile: **NULL, NULL, 4, 8, 8, 3**.

## Additional actually executed cases

Each listed rejection was executed three times on the same synthetic fixture.

| Case | MO result | Declared expected values / scope |
|---|---|---|
| `SUM(v)_filter` | rejected 3/3 | NULL, NULL, 4, 8, 8, 3 |
| `COUNT(*)_filter` | rejected 3/3 | 1, 1, 2, 2, 2, 2 |

## Working SQL control / alternative

The following control was executed **3/3** and its **complete output values** were checked, not merely execution success:

```sql
SELECT id,SUM(CASE WHEN flag=1 THEN v ELSE NULL END) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result
FROM (
  SELECT 1 id,1 gid,0 tick,CAST(NULL AS DOUBLE) v,CAST(2.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 2 id,1 gid,0 tick,CAST(2.0 AS DOUBLE) v,CAST(4.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 3 id,1 gid,1 tick,CAST(4.0 AS DOUBLE) v,CAST(3.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 4 id,1 gid,3 tick,CAST(4.0 AS DOUBLE) v,CAST(7.0 AS DOUBLE) y,CAST(3.0 AS DOUBLE) w,1 flag
  UNION ALL SELECT 5 id,1 gid,3 tick,CAST(NULL AS DOUBLE) v,CAST(5.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,0 flag
  UNION ALL SELECT 6 id,1 gid,8 tick,CAST(-1.0 AS DOUBLE) v,CAST(8.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,1 flag) fixture ORDER BY id;
```

| Control | Verified values |
|---|---|
| `sum_case_control` | NULL, NULL, 4, 8, 8, 3 |

DuckDB executed the equivalent window semantics and supplied the full expected output. The postfix IGNORE NULLS spelling is adapted to DuckDB's argument-level spelling without changing the requested semantics.

## Acceptance / regression coverage

Retain the self-contained fixture and assert complete values, NULL bits and row alignment. Add partitions, ties, empty/all-NULL frames, frame-entry/exit and type boundaries appropriate to this operator. Validate named/API availability separately from mathematical rewrites. Benchmark any claimed state/performance advantage with identical data and correctness rules; no speedup is asserted by these small tests.

Subsequent `SELECT 1` succeeded after the test matrix. DolphinDB references are official documentation; no DolphinDB runtime or all-parameter parity is claimed.

## Reference

https://duckdb.org/docs/stable/sql/query_syntax/filter.html
