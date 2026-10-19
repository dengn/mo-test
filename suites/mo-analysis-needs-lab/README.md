# Ten analytical needs: 100,000 MatrixOne workflows

Ten domains, each with ten independently described workflows and 1,000 parameter configurations: strict point-in-time features, incremental corrections, streaming events, causal analysis, attribution, hierarchical forecasting, temporal graphs, risk/simulation, spatial trajectories, and model monitoring.

Every main case executes SQL against MatrixOne. Python selects expected rows independently from the original synthetic sources; DuckDB checks the SQL reference. All returned rows, schema and values are compared. NumPy/pandas/SciPy/sklearn/NetworkX/Shapely then compute the analysis, checked against separately coded mathematical references. Scientific algorithms run in Python after retrieval. This is not a claim that MO natively implements those algorithms.

`scenario-catalog.json` describes all 100 workflows. `results/main-001/*.jsonl` contains the 100,000 complete case records: IDs, workflow, parameters, SQL, client, complexity, timings, raw-input receipts, final expected/actual results and full failure inputs where applicable. Source fixtures and SQL reconstruct successful raw inputs; final outputs are stored in full. `report.json` gives validated counts and scope. `index.html` provides a searchable index. Pilot failures are retained and do not count as main MO failures.

Source data: 19 synthetic tables, 87,672 rows, 32 units, 96 days, seed 20261012091. Backdated knowledge/revisions, tombstones, randomized and observational subjects, post-conversion touches, chronological flow cycles, antimeridian paths, real DST folds, delayed labels and duplicated/late events are deliberate.

## Reproduce

Use a dedicated test database and an existing MatrixOne test instance; Python 3.12, Java 17. Install `requirements.txt`. Set `MO_HOST`, `MO_PORT`, `MO_USER`, `MO_PASSWORD`, `MO_NEEDS_DATABASE` as appropriate. Defaults are local synthetic test settings. Setup refuses to overwrite nonempty source tables. Staging resets only this suite's private derived tables in the selected database.

```bash
mkdir -p inputs results attempts jars
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python data.py
python scenarios.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python run.py --mode pilot --indices 0,17,60,125,999 --workers 4 --tag pilot-new
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python run.py --mode main --workers 4 --tag main-new
```

Run directories refuse overwrite. `frozen-main/` holds the executed main code. `source-audit-before.json` and final audit compare every source row. Incremental checkpoints issue real INSERT/DELETE operations and update daily aggregates using deltas, checked against full independent reconstruction; rollback controls preserve totals. Streaming checkpoints execute MO `INSERT IGNORE SELECT`, exercise five lateness policies and replay every batch to verify deduplication; reference acceptance is independently simulated.

## Framework supplements and performance

```bash
python tools/frameworks.py prepare
JAVA_HOME=/path/to/java17 SPARK_LOCAL_IP=127.0.0.1 python tools/frameworks.py spark
JAVA_HOME=/path/to/java17 python tools/frameworks.py flink
python tools/performance.py
python tools/report.py
```

Spark validates 10,000 case groups in a shared actual Structured Streaming pipeline: JDBC source, event-time watermark, closed tumbling windows, aggregation, very-late-event drops, checkpoint stop/restart, and bounded MySQL-protocol transactional upsert sink. Flink validates 10,000 groups in a shared bounded JDBC source/join/aggregate/JDBC sink job; it includes late rows under complete-data semantics and makes no streaming watermark/recovery claim. These supplements do not replace any main case or count as 10,000 independent JVM pipelines. `tools/guard.py` wraps each framework with a 4 GiB process-tree RSS limit and 900-second deadline, terminating only that framework. Adjust its Java path before replay on a different machine.

Performance measures 200 serial warmed MO reads over 50 representative queries after main/framework jobs stop. Gold construction and equality checking are outside the clock; client fetch and DataFrame creation are inside. Main-run latencies include reference/scientific work and interference. There is no production-scale throughput claim.

Monitoring uses the original local server PID 1384 and paths in `tools/monitor.py`; update those for another instance. Memory pressure counters, OOM counts, process identity, RSS and disk evidence are separate from case results. No server restart or destructive chaos injection is used by this suite.

## Definitions and limitations

A case is an independently identified parameterized workflow assertion, not a new algorithm. Mathematical tolerance is rtol/atol 1e-6, SQL numeric tolerance 1e-7; IDs/integer counts and NULL masks are exact. Hierarchical reconciliation uses diagonal error weights. CVaR optimization scales a fixed portfolio direction. Spherical haversine distance is not an ellipsoidal geodesic. Model versions have independently generated scoring events, not paired predictions. Forecast future truth is used only for backtest scoring, and future covariates are known calendar values. Models' predictive quality and distributed production fault tolerance are outside this synthetic compatibility exercise.

`results/counterfactual/` additionally contains 50 real-MO point-in-time invariance controls (100 queries): future-only observations, dimensions and labels are perturbed in private copies. Every historical query result must remain equal. These are supplemental and do not add to the 100,000 main cases.

`results/coldstart/` contains 1,000 additional controls with 1–4 historical observations per unit, explicitly verifying forecast fallback. Dense main forecast template 8 has enough history and does not activate its fallback branch; those main records remain unchanged. These controls are supplemental, not replacements.

## Client NULL repair and final outcomes

The initial main code remains frozen. Some point-in-time analysis attempts passed full SQL equality but the Python scalar `np.isnan(None)` failed when an entire nullable column was `None`. `repaired/analytics.py` changes only those visibility checks to `pandas.isna`; SQL, references and tolerances are unchanged. `results/retest/` reruns recorded failures with fresh MO queries and full result/scientific validation. Final logical-case counts overlay those documented attempts; the initial 100,000 records and all failures remain intact. Repeated attempts do not create extra main case IDs.

For a corrected full replay, copy `repaired/*.py` and `requirements.txt` to a fresh directory, create `inputs/` and `results/`, initialize a new dedicated database with `data.py`, and run that directory's `run.py`. For a historical baseline replay, use the original frozen main modules.

The main run completed its first prefix with four threads, then `tools/continue_main.py` resumed missing IDs using three CPU worker processes and the same frozen evaluator. `results/main-001/continuation.json` records every completed prefix byte count/SHA, the process transition and unchanged code hashes. Final summary verifies all 100,000 unique IDs, every preserved prefix and unchanged code. This driver change is independent of the later documented NULL repair.

`results/speed-controls/` adds 100 controls using the held-out antimeridian cohort to include both positive and negative speed-anomaly classifications. Main template 4 cohorts mainly contain ordinary low-speed trajectories. These controls remain supplemental.

After restoration, `python tools/replay.py 65017` replays one case with the documented corrected evaluator and compares its complete scientific output to the preserved historical result. It audits original source fixtures before execution; incremental/streaming cases rebuild the required checkpoint in the suite's private derived tables. Replay result directories refuse overwrite.

The original continuation ledger has an empty-file record-count annotation error; `continuation-corrected.json` derives those counts from preserved prefix bytes. Prefix SHA/length, actual case records and verified final counts are unaffected. See `CORRECTIONS.md`.
