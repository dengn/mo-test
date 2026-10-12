# LAG/LEAD with an untyped NULL default return a recovered vector panic across partitions

This is a local draft; no new GitHub issue has been submitted.

Tested binary: MatrixOne commit `23d8f61252f3017dff218b530817a240206fd762`, MySQL text protocol, local single-node service. ClickHouse `26.9.16.11` runs the corresponding query successfully when its input is explicitly declared `Nullable(Float64)`; the recorded CH SQL preserves this type adapter.

```sql
SELECT point, eid,
       LAG(value,1,NULL) OVER(PARTITION BY eid ORDER BY point) AS result
FROM (
  SELECT 1 point,1 eid,CAST(1 AS DOUBLE) value
  UNION ALL SELECT 2,1,2
  UNION ALL SELECT 3,2,3
) f
ORDER BY point;
```

The expected values are `NULL,1,NULL`. The query returns MO error 20101 with `index out of range [2] with length 1`, including `Vector.propagateUniformStringSource`, `propagatePrepareParamKindsBatch` and `UnionBatch` stack frames. Replacing LAG by LEAD also fails; its expected values are `2,NULL,NULL`.

Controls on the same fixture pass:

* `LAG(value,1,CAST(NULL AS DOUBLE))` / corresponding LEAD: preserves NULL-default semantics.
* Omitting the explicit default: passes.
* An explicitly typed non-NULL default: passes.
* Two- and three-row single-partition fixtures: pass.

This demonstrates an execution error in an implemented function, not a missing function. The service remains alive with the same PID and health probes continue passing; this is a recovered query-level panic, not an observed service crash. The stack suggests constant-default metadata copying across partition offsets; that remains a hypothesis until traced in code.

The executable reproduction and all controls are in `null_default_repro.py`, `results/null-default-partitions.json` and `results/null-default-repro.json`. Searching GitHub for the exact stack symbol returned no issue; that does not establish that no related issue exists under other wording.
