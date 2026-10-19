# Issue #29927: old binary versus current main

Verified on 2026-10-13 (Asia/Shanghai). **The results support treating the original persistent index-metadata corruption as fixed on the tested main.** It reproduced on the reported old binary, whereas all five independent main runs passed subsequent usability, acknowledged-write and restart checks. This does not identify the exact fixing PR or prove every possible race interleaving safe.

Issue: https://github.com/matrixorigin/matrixone/issues/29927

| Check | Reported old version | Current main |
|---|---|---|
| Full commit | `2726fb419b3afa1db2686ae1b2aaca563d1ae214` | `3e50e1b32d8da61bbbf70c89989fb08b671809de` |
| Runtime `git_version()` | `2726fb4` | `3e50e1b3` |
| Independent fresh-database trigger runs | 3 | 5 |
| Runs exhibiting original persistent failure | 1 (third run) | 0 |
| Post-load `SHOW CREATE`, INSERT and HNSW REINDEX | Failed on affected table | Passed in every run |
| Graceful restart | Same original errors persisted | All five databases passed rechecks |
| Acknowledged background writes checked (id/n) | 608, none missing/wrong | 1,081, none missing/wrong |
| Background writer/reader client errors | Present in affected old run | 0 |
| Main DDL operation groups | — | 125: 78 completed, 47 rejected with code 20706 FastFail lock conflict |
| Main post-load and post-restart checks | — | 454, all passed |
| Unhandled panic/fatal/race log matches | 0 | 0 |

The exact published trigger was retained. Each run starts with four 500-row fixture tables (HNSW, IVF, FULLTEXT, FULLTEXT2), 8 writers, 24 readers and a 40-thread pool allowing up to 8 concurrent DDL workers. It executes 25 operation groups; some groups contain both CREATE and DROP statements. Only the loopback port and per-run output directory were changed. Main used isolated SQL 6014; the old binary used isolated SQL 6015 with a **new data directory**. Original historical 6001 data/WAL were not touched. Both instances used default pessimistic RC transactions, checked separately through the actual transaction view.

## Reproduced old symptoms

Third old run, database `index_race_repro_1791856570`:

```text
SHOW CREATE TABLE race_h:
ERROR 20101: internal error: missing visibility metadata for index "ridx_3" on table 272615

INSERT / HNSW REINDEX:
ERROR 1146: no such table index_race_repro_1791856570.__mo_index_secondary_01a132f9-7fcd-754d-aace-de89cecc4a20
```

Both failures persisted after graceful restart. The third run acknowledged 175 background writes; all 608 acknowledged writes across the three old runs were checked without missing IDs or wrong `n` values. No stronger claim about every stored vector/text byte is made.

## What passed on main

After every original workload, fresh connections checked SHOW CREATE and SHOW INDEX for all four tables, index catalog visibility and referenced physical index tables, the full acknowledged-write ledger, a new HNSW insert/reindex/query, IVF/fulltext2 reindex, and a new secondary-index CREATE/DROP followed by SHOW CREATE. After graceful service restart these checks were repeated for all five databases. There were no missing physical-index-table or visibility-metadata errors.

The 47 rejected concurrent DDL groups all reported `(20706, 'lock options conflict, wait policy is fast fail')`. These are distinguished from durable corruption: subsequent operations and restart checks passed, and background writers/readers reported no errors. A CREATE and later DROP are separate statements; if a later DROP is rejected, a surviving valid secondary index is legitimate. Referenced internal relations were checked rather than assuming every attempted index must be absent.

## Fix attribution and issue status

The issue already has an independent comment reporting 15/15 non-reproductions on another recent main. This report adds its own five-run evidence and a contemporaneous old-binary positive control; it does not adopt that comment's statistical independence assumptions.

Candidate merged PRs mentioned there are #29867, #29861, #29837 and #29472. Source inspection confirms they are merged, but no revert/bisect established which one removes this particular race. Some changes, such as quoting special index names, do not alone explain this ASCII-named reproducer. Therefore this report does not label any candidate the proven root-cause fix. The issue was still open when inspected; this task did not post comments or close it.

## Evidence and replay

- `comparison.json` gives the concise comparison; `summary.json` and `old-control/summary.json` preserve every run and actual client/DDL errors.
- `runs/run-*/index-race-output/` and `old-control/runs/run-*/index-race-output/` retain the original per-DDL results and acknowledged-write ledger. `verify-post_load.json` / `verify-post_restart.json` record every additional SQL and response.
- `original-reproducer.py` is extracted verbatim from the issue. `main-reproducer.py` / `old-reproducer.py` change only the port. `workload_entry.py` adds output metadata after execution; it does not change the trigger.
- `main-build.log`, runtime Git IDs and binary SHA256 establish the actual build. Main was built normally with Go 1.27.1 and fresh native dependencies in an isolated worktree; no product-code patch was applied. The old binary was the retained original build, not a new approximation.
- Initial transaction-view monitoring used an invalid alias-free query and produced diagnostic-only errors. Those attempts are preserved and are separate from background workload error counters. `check_mode.py` corrected the view alias and independently verified both services as Pessimistic/RC; `run_suite.py` includes the corrected monitor for future replay. The five race runs were not silently overwritten by a rerun.

For replay use a dedicated local environment with PyMySQL and the pinned binaries. Adapt `ISSUE_BINARY`, `ISSUE_OUTPUT_ROOT`, `ISSUE_EXPECTED_COMMIT`, `ISSUE_MO_PORT`, `ISSUE_RUNS` and `ISSUE_REPRODUCER` as needed, and point the config to a **new owned data directory and unused ports**. `run_suite.py` refuses to overwrite existing run folders. The old control is expected to return a failing assertion when corruption is reproduced; that expected nonzero exit is recorded, not interpreted as a harness success or a main failure.

Configuration, scripts and logs are uploaded; binaries, databases, caches and PID files are excluded. Each service started for this check was gracefully stopped when its verification finished. Original 600,000 main case counters are unchanged; this is a separate regression verification suite.
