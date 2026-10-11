# MatrixOne demand-driven analytical workflows

Forty distinct business questions, each with 250 entity/time/budget/service/risk configurations, form 10000 complete cases. The question and acceptance contract come first in catalog.py; SQL prepares the required business facts, and analysis.py produces the statistical result or decision. This batch is organized around analysis needs rather than a database function inventory.

Examples include accounting profit bridges, customer segmentation, cohort maturity, censored survival, lifetime value, user-level randomized experiment estimates and guardrails, multi-touch attribution, constrained marketing budgets, holdout demand forecasts, budgeted replenishment, assortment/category coverage, supplier concentration, ongoing-shipment SLA, ledger revision/as-of reconciliation, collections, stochastic liquidity, borrower-separated credit validation, portfolio covariance/tail risk/allocation, lagged pairs trading, price/promotion associations, historical-feature fraud review, session funnel/absorbing transitions, capacity, battery SOC dispatch, time-separated maintenance, multiple-comparison quality drift, machine censoring, Erlang staffing, customer health, deferred revenue, expansion, revenue anomalies and integrated procurement/capacity/cash planning.

## Meaning of a passed case

1. Every complete business fact dataset from MO matches DuckDB built from the original deterministic inputs. Integral fields are exact, continuous fields use rtol=atol=1e-7.
2. Pandas/NumPy/SciPy analyses run separately on reference facts and MO facts; metrics, diagnostics and decisions agree. After the raw fact comparison, model inputs are normalized to eight decimal places to make near-tie decisions deterministic.
3. Business invariants hold, including monetary allocation identities, nonnegative/integer/budgeted plans, censoring and temporal split rules, stochastic probability bounds, portfolio PSD/weight bounds, SOC balance, service levels, and deferred-revenue identities.
4. The actual MO-derived decision is persisted, read back and audited in MO against an independently constructed reference decision. Alternating cases publish/commit or cancel/rollback, then remove their private output rows.

Stage queries, checked rows and assertions do not become additional cases. Scientific algorithms on the two fact sets are the same implementation: this validates the MO integration; separate invariants and independently coded Pandas accounting/day-grid checks provide additional methodology controls. Synthetic results do not establish production predictive accuracy, statistical power or causal advertising/price effects. Normal forecast intervals are approximate.

## Data and evidence

Thirty synthetic tables contain 284281 rows. New fixtures add logistics, receivables, revisioned ledgers, experiments, demand/price observations, supply, credit snapshots, machine telemetry/production, hourly energy, support, contracts and device-linked payments. Explicit edge cases include no-purchase customers, missing credit, failed payments, superseded ledger rows, stockout-censored sales, ongoing shipments, immediately paused and right-censored subscriptions, and censored machine lifetimes. Subscription months use a standardized month index; current commerce days represent the last three historical months.

All source tables are compared in full before and after the run. Independent Pandas calculations reproduce revision/as-of accounting and calendar-day revenue. Missing-sales days count as zero calendar days. The initial sparse-day average was corrected during the run; the earlier partial attempt remains in results/canonical-before-calendar. Only 3000 unchanged successful workflows were retained after analytical/source-code hashes, original data hashes and exact SQL/parameters matched. Changed workflows were reexecuted; final IDs are exactly 0–9999 with no duplication. See calendar-correction-validation.json and canonical checkpoint metadata.

cases.jsonl contains every query, parameters, full final expected/actual analyses, decisions, constraints and publication statements. Successful fact matrices are represented by dimensions, full float-array hashes, and first/last row samples; every value was compared in memory. Full failing extracts are retained. The original inputs, exact SQL and code reconstruct the complete matrices. Hash differences between independently aggregated floats are permitted only after the numerical comparison passed.

## Reproduce

Use an isolated synthetic-data database. Configure MO_HOST, MO_PORT, MO_USER, MO_PASSWORD and optional MO_DEMAND_DATABASE; default database is ds_demand_20261011. Original source setup never overwrites an existing nonempty table. Private decisions_N work tables must be empty. Dependencies and Java 21/JDBC jar versions are recorded in environment.json. Python dependencies are pinned in requirements.txt; report plotting/browser requirements are optional.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPARK_LOCAL_IP=127.0.0.1
python -c 'from data import tables,setup; setup(tables())'
python verify.py
python run.py --pilot 3 --workers 4
python run.py --workers 6
python guard.py spark_supplement.py
python guard.py flink_supplement.py
python verify.py --final
python final_check.py
python performance.py
python plot.py
python report.py
python render.py
python package.py
```

For another instance, adapt the monitoring PID/server-log paths in run.py/final_check.py. JDBC jars are resolved from /workspace/mo-ds-lab/jars or the exported jars folder after adapting connectors.py. Spark uses READ_COMMITTED and analyzer maxIterations=500. Guarded optional clients have a 4 GiB RSS/600-second limit. Eight Spark and eight Flink workflows are supplemental, excluded from 10000; engine SQL executes the fact preparation, Python executes the scientific model, and decisions are stored through the MySQL protocol. The initial Spark full-floating-row ordering-key error is preserved separately and corrected by sorting actual business keys.

Canonical timings include local DuckDB/scientific/JVM contention. performance.json separately measures reads plus scientific decisions after compatibility clients end; it excludes publication and does not represent pure MO SQL QPS. Stability applies to the observed local four-CPU/16GiB window.
