# Published window-analysis feature issues and verified cases

20 English issues were published: **19 independently actionable feature requests and one coverage roadmap**. Every published body was fetched and checked against its reviewed draft. The existing regression issue was supplemented instead of duplicated.

**Roadmap:** [#29950](https://github.com/matrixorigin/matrixone/issues/29950).

## Issue index

| Capability | Issue |
|---|---|
| GROUPS window frames for peer-aware time-series analysis | [#29931](https://github.com/matrixorigin/matrixone/issues/29931) |
| EXCLUDE frame clauses for leave-one-out and peer-excluded analytics | [#29932](https://github.com/matrixorigin/matrixone/issues/29932) |
| IGNORE NULLS and non-NULL value navigation in windows | [#29933](https://github.com/matrixorigin/matrixone/issues/29933) |
| DISTINCT window aggregates for exact rolling unique metrics | [#29934](https://github.com/matrixorigin/matrixone/issues/29934) |
| FILTER clauses on aggregates and window aggregates | [#29935](https://github.com/matrixorigin/matrixone/issues/29935) |
| frame-respecting lagInFrame and leadInFrame navigation | [#29936](https://github.com/matrixorigin/matrixone/issues/29936) |
| non-negative time derivatives for irregular cumulative counters | [#29937](https://github.com/matrixorigin/matrixone/issues/29937) |
| native weighted sum and average aggregates with window support | [#29938](https://github.com/matrixorigin/matrixone/issues/29938) |
| native correlation and covariance aggregates with window support | [#29939](https://github.com/matrixorigin/matrixone/issues/29939) |
| sum2, skewness and kurtosis aggregate/window primitives | [#29940](https://github.com/matrixorigin/matrixone/issues/29940) |
| product aggregates with window support and zero/sign/NULL semantics | [#29941](https://github.com/matrixorigin/matrixone/issues/29941) |
| extrema positions within sliding frames with deterministic ties | [#29942](https://github.com/matrixorigin/matrixone/issues/29942) |
| allow max_by and any_value aggregates to compose with OVER | [#29943](https://github.com/matrixorigin/matrixone/issues/29943) |
| native exact weighted percentiles with window support | [#29944](https://github.com/matrixorigin/matrixone/issues/29944) |
| exponential-weighted statistics with explicit decay and NULL policies | [#29945](https://github.com/matrixorigin/matrixone/issues/29945) |
| bounded TopN-by-key window statistics with deterministic ties | [#29946](https://github.com/matrixorigin/matrixone/issues/29946) |
| local sliding-window ranks distinct from partition-wide RANK | [#29947](https://github.com/matrixorigin/matrixone/issues/29947) |
| valid-observation windows and reset-aware cumulative state | [#29948](https://github.com/matrixorigin/matrixone/issues/29948) |
| technical-indicator kernels and rolling risk analytics | [#29949](https://github.com/matrixorigin/matrixone/issues/29949) |
| window analytics compatibility roadmap with validated ClickHouse/DolphinDB gaps | [#29950](https://github.com/matrixorigin/matrixone/issues/29950) |

Existing regression supplement: [#10182 comment](https://github.com/matrixorigin/matrixone/issues/10182#issuecomment-6116266669).
The separate NULL-default execution bug remains [#29925](https://github.com/matrixorigin/matrixone/issues/29925).

## What was actually verified

- 297 final small, read-only MO queries: 240 expected syntax/name rejections and 57 executed controls whose complete values were checked, including NULLs. Every small case has three recorded runs. These are supplemental validations, not 297 new canonical analytics cases.
- DuckDB executes GROUPS/EXCLUDE/IGNORE NULLS/DISTINCT/FILTER references. NumPy/SciPy independently calculates the declared statistical profiles.
- Four live ClickHouse 26.9.16.11 controls verify frame-aware LAG/LEAD, a three-row derivative profile and an exact weighted percentile.
- The existing ten-row, 17-column MO mathematical rewrite was fully rechecked against independent expectations.
- Subsequent SELECT 1 succeeded. This tiny matrix is not a throughput, long-soak or distributed-failover benchmark.
- Current main-suite totals stay 260,000 canonical cases; the previous 10,000 time-series main results remain 9,800 pass / 200 unsupported-frame failures.

`validation.json` contains full SQL, expected/actual arrays, error messages, repetitions and reference data. `cases.json` is the initial fixture/probe catalog. `payloads.json` and `drafts/` preserve the exact English issue content; `published.json` and `publication-verification.json` capture links and readback checks. `dedup.json` retains search titles/links and reviewed older issues.

## Scientific and compatibility limits

An absent same-name API does not mean the business formula is impossible. Dedicated-name probes explicitly test name resolution; they are not valid-signature/all-parameter assertions about DolphinDB. Common math can already be composed using MO SQL. Exact and approximate algorithms, biased/unbiased estimators, Pearson/excess kurtosis, NULL eligibility, ties, state interfaces and frame boundaries must be compared separately. DolphinDB was documented, not run live.

Ordinary max_by/any_value, explicit RESPECT NULLS, BIT_XOR OVER, ordered-set percentile and native INTERVAL/SLIDING/FILL are recognized as existing capabilities. A currently rejected OVER combination is not reported as absence of the ordinary function. Linear regression is tracked by the existing #10182; other closed fixes are not reopened just because an older report once showed a rejection.

The derivative CH correctness reference re-encodes the same three rows with numbers/arrays. The CH UNION literal shape returned zeros and was not used as an oracle. Early attempts at a TopN rewrite hit an MO UNION/CTE projection-remapping error; the final control uses the identical values generated with CASE/generate_series and compares every output. The failed prototype and log are retained in `attempts/`, excluded from the 297 final matrix. No speedup or all-shape equivalence is inferred.

## Re-run

Copy the entire `research/window-gap` directory to a **new run directory** first; these scripts overwrite their own output files. Install `feature-issues/requirements.txt`, set MO_HOST/MO_PORT/MO_USER/MO_PASSWORD and MO_TS_DATABASE to an existing dedicated synthetic test database. No source tables are required. Set CLICKHOUSE_BINARY to the pinned official binary described in the parent README.

```bash
cd feature-issues
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python validate.py
python add_profiles.py
python final_controls.py
```

The final namespace probes and controls deliberately retain unsupported cases instead of changing a frame or API and counting it as native success. Public issues include only necessary synthetic SQL, outcomes and the public tested commit, with no credentials, internal environment paths, binary fingerprints or private repository links.
