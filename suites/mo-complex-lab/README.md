# MatrixOne complex analytics compatibility lab

This is a separate batch from `/workspace/mo-ds-lab`.

Canonical execution: 80 complex SQL definitions plus 20 client numerical/ML pipelines, each with 1000 distinct parameter tuples. 100000 unique case IDs; each performs an actual MO query. Pandas/SQLAlchemy and PyMySQL/NumPy each run 50000 cases. Case IDs identify scenario * 1000 + parameter.

Independent SQL oracle: DuckDB 1.3.2 loaded from deterministic original data, not from MO outputs. All source table contents are verified, plus 168 independent Pandas/NumPy checks of six analytical definitions. Client algorithms use the same numerical code for both independently extracted feature matrices; this verifies interoperability and does not independently prove the numerical algorithm implementation.

SQL scenarios include multi-table reconciliation, cohorts, temporal funnels and attribution, nested windows, rolling statistics, regression sufficient statistics, robust loss, entropy/mutual information, graph traversal and motifs, recursive CTEs, correlated queries, full joins, grouping sets, rollup and percentile. Scientific arithmetic explicitly requests DOUBLE, including integer averages and decimal literals; initial default-decimal pilot remains in separate results.

## Run

Use dedicated synthetic-data databases. Set MO_HOST, MO_PORT, MO_USER, MO_PASSWORD and optionally MO_COMPLEX_DATABASE; defaults target the dedicated local MatrixOne test instance. Existing tables must contain the original deterministic dataset. Source data is never reset automatically.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPARK_LOCAL_IP=127.0.0.1
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/run.py --setup --pilot 10 --workers 8
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/verify_data.py
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/run.py --workers 8
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/connectors.py spark
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/connectors.py flink
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/analyze_failures.py
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/performance.py
/workspace/mo-ds-venv/bin/python /workspace/mo-complex-lab/summarize.py
```

Spark/Flink each execute 10 genuinely complex JDBC source/computation/sink pipelines with 1000 independent customer assertions per pipeline; those 20000 assertions are supplemental and never added to the main 100000 count. Spark uses explicit READ_COMMITTED. JDBC jars are bundled from the prior lab. Set MO_JAR_DIR to override the jar directory. Process/RSS and server-log capture in this local run refer to /workspace/mo-ds-lab/server.pid and server.log; adapt those paths when rerunning on another host.

Measurements are local observations on four CPU quota, 16 GiB RAM, one MO instance. Main-run timings include contention with DuckDB/client calculations. Dedicated performance measurements are run after compatibility and connector work complete. Successful connector runs were separate from the main workload. No long-duration or multi-node crash/HA guarantee is inferred.

Flink uses top-level Table API CTE views and explicitly quotes Calcite reserved identifiers. Two failed client SQL setup attempts are preserved under flink-harness-first/second; they are excluded from the final supplemental result count and are not MatrixOne execution failures. Canonical main workload did not overlap the Spark/Flink runs: an initial attempted connector start was blocked before execution, and successful runs started after canonical completion.

Performance: a 2048-query calibration showed warm-up/order variation and is retained separately. Final measurement uses 64 prewarming queries, then three balanced-order trials per concurrency (1024 measured queries each): 12288 total measured queries; result assertions are outside timed work. No compatibility rerun is counted as a canonical pass.
