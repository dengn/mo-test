# Executed regression baseline

These are actual local executions of the portable suite on 2026-10-13, not a claim that all ten BI tools are compatible. The tested MatrixOne build is `23d8f61252f3017dff218b530817a240206fd762`, binary SHA256 `49d2d31eeb6c8b3151612aa10314c1081cb47908410e7321fae389b0db0c80e7`. Runtime versions and official image/release identities are in [runtime-pins.json](runtime-pins.json). This is a fixed-build baseline, not validation of the current MatrixOne main branch.

## SQL and input integrity

| Profile/check | Executed | Passed | Recognized failures |
| --- | ---: | ---: | ---: |
| Strict smoke | 732 | 732 | 0 |
| Full analytical SQL | 20,534 | 20,334 | 200 |
| Bounded extreme/long SQL | 257 | 257 | 0 |
| Operator spill | 14 | 14 | 0 |
| Managed spill recovery/resource limits | 6 | 6 | 0 |
| Runner contract unit tests | 25 | 25 | 0 |

The 200 SQL failures are the exact correlated range-aggregate signature tracked in [MatrixOne #28298](https://github.com/matrixorigin/matrixone/issues/28298). Each error was followed by a successful check on the same connection. They remain failures in strict mode; the observed full run is not a green compatibility gate. Correct results after an engine fix must match the existing independent answers.

The default extreme profile replayed the 257 historically bounded successful cases, including very long SQL, in about 142 seconds. The other 11 imported boundary cases are retained and explicitly unselected by default, not silently marked passed. Full output comparisons ran; the initial extreme receipt contains completed case IDs and timings from JUnit rather than output hashes.

All five compressed SQL/MBQL/metrics packs passed SHA/count/unique-ID checks. The deterministic 14-table core regenerated exactly 356,840 source rows with the frozen CSV hashes; database contents were audited field by field. The independent answers were imported from the original Python/DuckDB/CSV checks and were not generated from these MatrixOne executions. Locked Python wheels installed with `--require-hashes`; the final smoke and full SQL runs used that environment.

## Actual native BI paths

| Tool | Executed checks | Passed | Recognized failures | Actual coverage and limitation |
| --- | ---: | ---: | ---: | --- |
| Metabase | 6,880 | 6,880 | 0 | 6,820 MBQL, 10 saved metric checks, 50 dashboard-filter requests on 24 fresh explicit SQL models; automatic grants/field sync is not asserted |
| Superset | 553 | 109 | 444 | SQL Lab, view reflection, physical-table saved metrics and chart-data; precise tuple/DECIMAL and NullType diagnostics remain failures |
| Grafana | 535 | 0 | 535 | Actual MySQL datasource health and query APIs; the handshake's invalid connection is preserved, including the health API's `details.verboseMessage` |
| Redash | 534 | 492 | 42 | Official MySQL runner and production JSON encoder; float conversion loses exact money values; no complete Web scheduler coverage |
| DataEase | 535 | 531 | 4 | Save a native datasource and call SQL preview; four 100-row previews are truncated and remain failures; no complete chart/cross-datasource coverage |
| Evidence | 534 | 0 | 534 | Official mysql plugin `rows()` with no collation monkey patch; closed-connection failures; no native page build success |
| Rill | 800 | 511 | 289 | Actual MySQL ingestion and ten local metrics views; DOUBLE precision differences; aggregation runs in Rill's local DuckDB |
| Zeppelin | 534 | 533 | 1 | Saved JDBC paragraphs; a tab/newline TABLE serialization difference; not an engine value error |
| SQLPad | 535 | 535 | 0 | Native REST batches, completion/full results and a saved query |
| Lightdash | 4 | 0 | 4 | Official warehouse factory/SQL builder reject unsupported MySQL/MatrixOne adapters; no MatrixOne SQL executed |

Known client value differences require both the complete historical failure-value fingerprint and a current direct MatrixOne source query matching the independent answer. They are not accepted as correct BI results. Unknown errors, missing runtimes, new differences and incomplete results fail even in observe mode. Counts overlap across tools and are not additions to the repository's unique historical case count.

Superset's dedicated official server used the supported Flask-AppBuilder `FAB_API_SHOW_STACKTRACE=True` setting to expose the precise reflection failure. A generic `Fatal error` remains unknown in the adapter. Deployment configuration, asynchronous datasource/model startup and runner bugs encountered during migration were fixed separately; they are not reported as MatrixOne defects. Earlier attempts remain distinct from the final attempts listed in [validation.json](validation.json).

## Real spill and recovery assertions

The operator fixture has 1,048,576 wide fact rows. Thirteen positive operator cases passed full-stream result hashes and evidence from plans/counters/files, including unlinked open files under `/proc/<pid>/fd`. The NULL-aware `NOT IN` case returned the independent empty answer with no spill, an intentional negative control. Every case checked cleanup and `SELECT 1` on its original connection. Selected peak observed spill bytes were approximately 365 MB for grouped distinct, 303 MB for multiple distinct and 158 MB for the window query; these are observed file sizes, not throughput benchmarks.

The six managed checks started and stopped only runner-created MatrixOne children in a new private data directory:

1. Forced wide sort: complete reference hash, approximately 49 MB observed spill, no temporary files remaining.
2. Cancellation: sent `KILL QUERY` only after real spill was observed; received `context canceled`, cleaned files, original connection remained usable.
3. Million-row wide sort at 128 MiB: controlled `allocation account capacity exceeded`; parsed used/requested/limit confirm the configured quota. Original connection and cleanup passed.
4. Wide sort with 1 MiB spill capacity: controlled spill disk budget rejection and healthy original connection.
5. High-cardinality aggregate with 1 MiB spill capacity: controlled spill disk budget rejection and cleanup.
6. The same million-row wide sort at 512 MiB: all 1,048,576 rows matched independent hash `e4a50f63402e977385d0b5730af2cbe1a1dd15a7d9c94ebf8a66ed02e98a9295`, approximately 195 MB real spill, complete cleanup and healthy original connection.

These resource rejections pass explicit protection contracts; they are not successful analytical outputs. Future implementations that correctly finish the low-resource queries can pass the recorded boundary-acceptance branch. Only the final wide-sort check requires the complete million-row output and real spill together.

## Inspectable receipts and CI scope

[validation.json](validation.json) identifies the exact final attempt, target, counts, receipt format and original result-file hash for every profile/tool. [validation/cases.jsonl.gz](validation/cases.jsonl.gz) contains sanitized per-case statuses, available output hashes, differences and reduced spill/recovery evidence. Open-file names and private runtime configuration are omitted. These receipts are diagnostic history, never the expected-result oracle.

[artifact-manifest.json](artifact-manifest.json) freezes the publishable suite and workflow files; `verify.py` checks those hashes before ordinary SQL/BI execution and managed recovery. JSON/JUnit are generated anew on every invocation. The reusable/manual workflow was added but not dispatched remotely, and no nightly schedule was enabled. Self-hosted runner credentials, dedicated service endpoints and native runtime provisioning remain operator configuration.
