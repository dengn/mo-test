# MatrixOne cross-domain SQL and scientific-computing lab

This batch extends the demand-driven tests with two wide fact graphs and twenty business decisions, 500 configurations each. It defines 10000 complete main workflows, not 10000 independent question definitions. A customer graph references 19 source tables; a product/factory graph references 19. Both include nested derived relations, correlated scalar subqueries, EXISTS/NOT EXISTS, nested anti-existence tests, IN with a correlated predicate, dense calendar grids, revision/as-of snapshots and analytic windows. Data is synthetic: the same 30 deterministic source tables (284281 rows) from the preceding batch are loaded into a separate database, ds_cross_20261011.

## Three paths

* The main NumPy path reads a complete graph through PyMySQL and performs robust standardization/interactions, covariance shrinkage, Huber ridge, borrower holdouts, bootstrap, logistic calibration, PCA/clustering, mixture EM, graph fixed points, correlated Monte Carlo tail estimates, routing LPs, constrained budgets or simplex allocation. Each mission uses the relevant chain. NumPy/SciPy are used directly.
* The main pandas path runs the graph SQL through pandas/SQLAlchemy and independently builds the same wide facts from MO source snapshots using validated merge, groupby, rolling windows, anti-joins, aligned transformations and dense grids. Native pandas facts are reused within each parameter/domain across its ten business questions. The native source graph is checked against both SQL results and an original-data DuckDB reference. The scientific computation uses pandas preprocessing plus NumPy/SciPy.
* The separate Spark suite uses 10 configurations for each of the 20 questions: 200 complete workflows, excluded from the main 10000. It caches 30 JDBC source tables, runs the full fact graph in Spark SQL, and runs native windows, grouped aggregates, joins, repartitioning, StandardScaler, PCA and KMeans. It then runs each question's pandas/NumPy/SciPy scientific computation inside Spark Python workers with grouped Arrow execution. Spark JDBC publishes actual decisions, which are independently read back through PyMySQL. Ten questions share each verified fact graph and native ML pipeline.

Another 100 long workflows link both wide graphs through the actual customer-product purchase grain, covering the union of all 30 source tables. A pandas pivot builds the sparse customer-product exposure matrix; credit calibration and robust demand regression feed a correlated 128×14×80 demand tensor. Supply and credit shocks drive a CVaR epigraph LP with 209 variables and cash, energy, carbon and eight plant-capacity constraints. Procurement is rounded down to integers, every resource constraint is rechecked, and the actual decisions are published/read/cancelled or committed in MO. These are 100 complete business plans, excluded from both the main 10000 and Spark 200; tensor cells and Monte Carlo scenarios do not inflate counts.

Fifty additional feature-store workflows place the customer, product/factory and transaction bridge graphs inside three scoped CTEs of one SQL statement. Parsed source-name statistics show 30 different source tables, 47 JOIN tokens, 57 SELECT tokens and six EXISTS tokens in the approximately 15 KB SQL. These are text statistics including nested subqueries, not runtime operator counts. Every full 85-column customer-product fact matrix is compared with DuckDB and independently rebuilt with native pandas. Regional/category exposure pivots are checked with NumPy indexed accumulation, followed by robust PCA, resource-constrained allocation and transaction readback/visibility. The 50 are separate from all other batches; no Cartesian padding is added.

Native Spark scaling, PCA variance/projection/orthogonality and cluster distances/membership are checked independently with NumPy. The scientific algorithm on reference facts and MO/Spark facts is the same implementation; this is an integration test supported by independent fact implementations and physical/business constraints, not independently implemented scientific algorithms for all missions. Model outputs from synthetic fixtures do not prove forecasting accuracy, causal effects, statistical power or production risk-model validity. Snapshot regressions describe associations. Bootstrap/scenario distributions use the stated synthetic assumptions.

## Pass definition and evidence

Every complete fact matrix agrees with the original-source DuckDB result: integer/discrete fields exactly, continuous fields with rtol=atol=1e-7. Full data audits use 1e-12. Raw facts are checked before scientific input normalization to eight decimals, and feature arithmetic is normalized to ten decimals for deterministic near ties. Scientific outputs use 1e-6 comparison and independent resource/probability/accounting checks. The main pandas graph is an independently implemented reference and execution path, not a copy of the SQL. Native pandas and NumPy feature transformations must agree to 1e-12.

Each main workflow saves the full expected/actual final model, decisions, diagnostics, business checks and SQL. Successful fact matrices retain shape, column names, full-array SHA256 and row samples; every value was compared in memory. Original inputs plus the code reconstruct all facts. Main actual decisions are inserted, read and aggregated in a transaction, then alternately committed or rolled back, with visibility checked and private work rows removed. Spark publishes through JDBC and checks every decision row. Queries, cells, assertions, native ML stages and output rows do not become additional cases.

Original precision and client failures are retained separately in attempts. Uncast AVG(integer) in MO produced DECIMAL scale-four values, while DuckDB/Spark used floating results; the scientific SQL explicitly casts AVG arguments to DOUBLE. The numerical comparison threshold was not widened. Java 21 failed Spark Arrow direct-buffer access; Spark is run with Java 17.0.20.1 and the required module/Netty options. These are distinct from new database query failures. Final report outcomes are derived from the recorded cases.

The first full Spark attempt stopped at an independent standardization check: a mathematically constant stockout_rate had NumPy two-pass std≈2.1e-17, whereas Spark Welford correctly returned zero. The checker now explicitly treats exact constant training columns as zero-variance and zeroes them, matching StandardScaler's documented zero-variance behavior. The 30 passed workflows and failed attempt are archived, excluded from the final 200, and the full Spark suite is rerun. Numerical thresholds remain unchanged. Early 20-table wording counted incorrectly; parsed source-name statistics show 19 distinct tables in each graph and a 30-table union.

## Reproduce

Use an isolated synthetic database and Python 3.12 with requirements.txt. Set MO_HOST, MO_PORT, MO_USER, MO_PASSWORD and optional MO_CROSS_DATABASE. Monitoring paths target this workspace and should be adapted on another machine. Original setup refuses mismatched nonempty source table sizes; audits check full contents. Only private test work tables are written during the runs. The JDBC jar and exact runtime/binary/source-build metadata are included in environment.json. MO results apply to the binary build commit, which differs from the workspace checkout.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPARK_LOCAL_IP=127.0.0.1
python preflight.py
python run.py --pilot 3 --workers 3
python run.py --workers 6
JAVA_HOME=/path/to/java17 python spark_run.py --pilot
JAVA_HOME=/path/to/java17 python spark_run.py
python holistic.py
python joined.py --pilot
python joined.py
python audit.py
python performance.py
python final_check.py
python log_taxonomy.py
python capture_trace_sample.py
python export.py
python plot.py
python report.py
python render.py
python package.py
```

Spark resolves the MySQL jar from MO_JAR_DIR, the exported jars folder or /workspace/mo-ds-lab/jars. Configure the correct Java 17 JAVA_HOME and Python environment. Spark uses READ_COMMITTED. Optional client resource guards terminate only the test client tree, never MO. This is a local four-CPU, 16GiB execution window; isolated performance measures end-to-end reads/analysis, not pure server SQL QPS or production-scale capacity.

Final log evidence retains internal statement_info TEXT overflow contexts, RC metadata-retry entries, TN scheduling-poll entries and table-statistics context. Counts are log entries, not extra failed business cases. A current-database successful request has a valid 334391-byte execution-plan JSON in an ETL upload failure file, matching that upload's offending length and exceeding the 65535-byte TEXT limit. Many upload records refer to files predating this batch; the sample does not attribute every background failure to the new tests or prove permanent loss. Related existing issues are #29809 and #29797. Full log classification and the original sample are exported.

The first performance attempt overlapped the final source audit briefly and included concurrent reference-check overhead; it is retained separately and excluded. The final 480 measurements run after other clients/audits end; reference and constraint checks execute after each timed batch. Main case counts and execution hashes are unaffected.
