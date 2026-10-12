## Description

A three-row, two-partition query using `LAG(value, 1, NULL)` or `LEAD(value, 1, NULL)` returns a recovered query-level panic. Changing the default to `CAST(NULL AS DOUBLE)` avoids the error but returns **0 instead of NULL** in the final one-row partition. Omitting the default produces the correct result.

Tested MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`.

## Existing issue check

- [x] Checked existing issues.
- Related #23969 reports incorrect LAG/LEAD results but does not describe this explicit-NULL-default panic. #25906 concerns a huge offset; the valid offset here is 1.

## Reproduction

No tables are needed; all input is synthetic literal data. Run each query independently:

```sql
SELECT point, eid,
       LAG(value, 1, NULL) OVER (PARTITION BY eid ORDER BY point) AS result
FROM (
  SELECT 1 point, 1 eid, CAST(1 AS DOUBLE) value
  UNION ALL SELECT 2, 1, 2
  UNION ALL SELECT 3, 2, 3
) f
ORDER BY point;

SELECT point, eid,
       LEAD(value, 1, NULL) OVER (PARTITION BY eid ORDER BY point) AS result
FROM (
  SELECT 1 point, 1 eid, CAST(1 AS DOUBLE) value
  UNION ALL SELECT 2, 1, 2
  UNION ALL SELECT 3, 2, 3
) f
ORDER BY point;
```

Repeat with the third argument replaced by `CAST(NULL AS DOUBLE)`, and separately with the third argument omitted.

## Expected results

| point | eid | LAG | LEAD |
|---:|---:|---:|---:|
| 1 | 1 | NULL | 2 |
| 2 | 1 | 1 | NULL |
| 3 | 2 | NULL | NULL |

Untyped NULL, typed NULL and omitted defaults should all return these values.

## Actual results

Both original queries return:

```text
ERROR 20101 (HY000): internal error: panic runtime error:
index out of range [2] with length 1
```

| Default argument | LAG values | LEAD values | Repetition |
|---|---|---|---|
| `NULL` | panic/error 20101 | panic/error 20101 | each 3/3 fails |
| `CAST(NULL AS DOUBLE)` | NULL, 1, **0** | 2, NULL, **0** | each 3/3 has the wrong final value |
| omitted | NULL, 1, NULL | 2, NULL, NULL | each 3/3 correct |
| `CAST(0 AS DOUBLE)` | 0, 1, 0 | 2, 0, 0 | each 3/3 correct for a zero default |

The 24-query repeat matrix contains 6 panic errors, 6 typed-NULL wrong results, and 12 correct omitted/zero-default controls. `SELECT 1` succeeded afterward; no service crash was observed.

## Impact / regression coverage

Valid explicit-NULL-default SQL fails, while the typed-NULL form can silently produce incorrect analytical values. Typed NULL is not a valid workaround; omitting the default is correct on this fixture.

Please cover LAG and LEAD over multiple partitions, including a one-row final partition, with untyped NULL, typed NULL, omitted and non-NULL defaults. Assert all values and NULL bits, rather than only successful execution.

