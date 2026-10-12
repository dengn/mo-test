# MatrixOne physical column boundary probes

Tested binary: `main` commit `2726fb419b3afa1db2686ae1b2aaca563d1ae214`.
Environment: 4 CPU quota, 32 GiB cgroup limit, single local LOG/TN/CN process,
DISK-V2, default 64 MiB `max_allowed_packet`.

These are follow-up probes **outside the earlier 600,000 main cases**.

## Results

The base schema has distinct `INT` columns and a primary key on the first
column. One row contains value `i` in column `i`; full reads independently check
every value, name and order. Counts below exclude hidden columns.

| User columns | CREATE seconds | Result |
|---:|---:|---|
| 1,000 | 0.087 | CREATE, full INSERT, SELECT *, UPDATE/read passed |
| 10,000 | 1.520 | CREATE, full INSERT, SELECT *, UPDATE/read passed |
| 65,530 | See results.jsonl | All of the above passed; forced flush returned OK, followed by a successful full-value read |
| 65,531 | 20.632 | CREATE and INSERT succeeded, but final column read NULL instead of 65,531 |
| 65,532 | 22.598 | CREATE and INSERT succeeded; last columns read incorrectly; SELECT * oracle failed; updating last column still read NULL |
| 65,533 | 19.786 | CREATE caused unhandled panic and process exit |
| 100,000 | 32.599 | CREATE caused the same unhandled panic and process exit |
| 1,000,000 | 930.299 client duration | Query cancellation sent at the 900-second deadline; client timed out. User then stopped this scale. No table remained and no residual probe connection was found. This is not an established maximum or confirmed fatal reproducer. |

For this schema, **65,530 is the largest tested count with correct full-row
read/write and a post-flush full read**. This is an empirical boundary for this
simple schema and fixture, not a production guarantee for all data types,
indexes, workloads or hidden-column combinations. No million-column rerun was
performed after the user requested its cancellation; that size is excluded
from the runner defaults.

## Confirmed issue

[matrixorigin/matrixone#30011](https://github.com/matrixorigin/matrixone/issues/30011)
was filed in English with an inline reproducer and stack trace, then updated
with the smaller 65,533-column fatal reproduction and the preceding read errors.

```text
panic: bad column idx 65533, table wide_65533
pkg/vm/engine/tae/catalog/schema.go:962
```

`SEQNUM_UPPER` is 65,530. User columns at zero-based sequence 65,530 and above
enter a reserved range in several storage/read paths. `Schema.Finalize` panics
at zero-based column index `SEQNUM_COMMITTS` = 65,533.

After recovery, reading the offending tail of the 65,532-column table returned
SQL error 20101 with a recovered panic, `bad path to read special column 65530`.
The service stayed available. OOM and OOM-kill counters stayed zero across the
probes. The earlier 1,000- and 10,000-column rows still matched every value.

`ALTER ADD COLUMN` also applies an inconsistent limit: an explicit-PK table
created with 4,095 user columns rejects adding one column (1117), whereas one
created with 4,096 accepts two additions and reaches 4,098. Without an explicit
PK, the corresponding rejection is at 4,094 user columns. Batch addition to
the 4,095-column explicit-PK table was rejected atomically. All observations and
metadata counts are in `alter-results.json`.

## Artifacts and reproduction

- `test_columns.py`: materializes submitted SQL as deterministic gzip, records
  statement timing/result/error and service health, and samples resources.
- `test_alter.py`: CREATE/ADD comparison around 4,096 with/without explicit PK.
- `sql/`: exact submitted SQL, including the cancelled million-column request.
- `results.jsonl`, `steps.jsonl`, `65531-tail-results.json`, `flush-results.json`:
  original outcomes; failures are retained rather than replaced by rechecks.
- `panic-*.log`, `server-before-*.log.gz`: fatal evidence and archived logs.
- `recovery-after-100000.json`, `final-health.json`: successful recovery and
  retained valid rows. The first `recover.py` 65,533 follow-up used a five-second
  read timeout for a very wide SELECT and timed out while verifying it; that
  failed check is preserved. Subsequent health and bounded read checks establish
  recovery and separately record the offending tail error.
- `million-stop.json`: verifies no residual million-probe connection and a
  healthy SELECT 1 after the user's stop instruction.

Use a disposable instance: fatal probes terminate the combined mo-service
process. For example, `python test_columns.py --sizes 65533` reproduces the
fatal boundary. Connection defaults target the existing local stress instance.
`recover.py` refuses to restart a live service and archives logs before
restarting an already exited process. Scripts never modify MatrixOne source or
raise server column/packet settings.
