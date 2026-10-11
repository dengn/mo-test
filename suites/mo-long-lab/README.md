# MatrixOne long analytical combinations — independent batch of 10000

50 definitions × 200 distinct parameter tuples, 10000 actual complete case executions. 8000 long SQL combinations plus 2000 transactional staged analyses. Source data are synthetic: fourteen tables, 153656 rows; no production data used. Source DB defaults to ds_long_20261011 and can be changed with MO_LONG_DATABASE.

Long queries combine four to eight analytical blocks, up to 69 dependent CTEs, 63 window expressions, 31 joins, 21 nonlinear feedback steps and about 15.9 KB per SQL statement. Feedback recurrences use the previous score and transformed feature values; they change results rather than padding query length. Risk scores are synthetic numerical analytics, not a trained production risk model.

Each of the 2000 staged cases has 15–16 database operations: independent SQL feature extraction, transactional bound-row insertion, independent readback, server-side window transformation and intermediate materialization, grouped diagnostics, commit/rollback visibility, UPDATE/read-own-write/rollback preservation, cleanup. Steps do not inflate the canonical case count. Per-case SQL, intermediate statement logs, expected/actual values and timings are retained.

DuckDB 1.3.2 is constructed from the original deterministic data. All fourteen MO tables are compared in full; market/subscription blocks have independent Pandas calculations. Integral counts are exact and numerical comparisons use rtol=atol=1e-7. Ranking uses explicitly rounded floating sort keys and deterministic cid tie breakers. Island arithmetic casts window ordinals to signed BIGINT; RETENTION, a reserved alias, is renamed active_retention. The first dialect/type pilot is retained separately and excluded from canonical counts.

## Reproduce

Configure MO_HOST, MO_PORT, MO_USER, MO_PASSWORD and optionally MO_LONG_DATABASE. Use a dedicated synthetic-data instance, Java 21 and the pinned Python dependencies. Stage tables are private to each worker and must be empty before a run. Original source data are not reset.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPARK_LOCAL_IP=127.0.0.1
python run.py --setup --pilot 4 --workers 4
python verify_data.py
python run.py --workers 8
LONG_SPARK_ANALYZER_ITERATIONS=500 python connectors.py spark
python guard.py flink_bounded.py
python final_check.py
python performance.py
python plot.py
python report.py
python render.py
python package.py
```

JDBC jars are resolved from this folder's jars subdirectory or /workspace/mo-ds-lab/jars; override with MO_JAR_DIR. Process monitoring/server log capture refer to the dedicated local server.pid and server.log in /workspace/mo-ds-lab. Adapt these paths for another host.

Spark and Flink supplemental long chains are excluded from the main count. Spark uses explicit READ_COMMITTED. Their planner/runtime/dialect limitations are classified separately from MatrixOne SQL execution. Main workload timings include local oracle/client CPU contention and supplemental workloads; isolated performance measurements run after all compatibility work ends.

This is local execution on four CPU quota and 16 GiB RAM. Stability evidence applies to this window and workload, not distributed HA, restart recovery or production-scale capacity.

The monolithic Spark default analyzer ran one chain and rejected the longest at its 100-iteration resolution cap; both chains passed with analyzer maxIterations=500. The quoted monolithic Flink attempt consumed excessive planning time/memory and its test-owned processes were stopped. Materializing only feature blocks still crossed the 4 GiB client guard. The successful equivalent materializes feature blocks, normalization, and feedback chunks of three layers, under a 4 GiB client process-tree RSS / 600-second guard. All intermediate tables and 2000 final outputs passed, compared to the original unmaterialized DuckDB program. These supplemental results and incomplete planning attempts are separate from canonical MO cases.

Full-precision deterministic inputs are included as fourteen inputs/*.csv.gz files. dataset-manifest.json hashes use the normalized CSV representation with float_format='%.12g'; artifact-manifest.json hashes the actual exported files. Per-case SQL and outcomes are retained in cases.jsonl, with examples/longest.sql and examples/multi-stage-complete.sql for individual inspection. The latter uses separate example work-table names.

Final results: 10000/10000 canonical cases passed; Spark 2000/2000 and bounded Flink 2000/2000 supplemental output checks passed. There were 282 internal statement_info ingestion failure events during the canonical window. A retained successful user-query record has valid exec_plan JSON of 598222 bytes, above ordinary TEXT capacity 65535; stored statement is 1027 bytes. This is an existing MO observability defect tracked by https://github.com/matrixorigin/matrixone/issues/29797 and https://github.com/matrixorigin/matrixone/issues/29809. No duplicate issue was submitted. Raw record and events are included under telemetry/. User query prefix was truncated in tracing, so candidate-user-cases.json contains possible matches, not a uniquely established case ID.
