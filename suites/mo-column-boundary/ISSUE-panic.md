### Is there an existing issue for the same bug?

Searches for `"bad column idx"` and `"65533"` in this repository returned no existing issues at the time of filing.

### Branch and version

`main`, commit `2726fb419b3afa1db2686ae1b2aaca563d1ae214`.

Built with Go 1.27.1 and SIMD enabled. `SELECT VERSION()` returns `8.0.30-MatrixOne-v`.

### Actual behavior

A `CREATE TABLE` statement with 100,000 ordinary `INT` columns, with the first column as the primary key, reaches the TN storage layer and causes an unhandled panic:

```text
panic: bad column idx 65533, table wide_100000
```

The `mo-service` process exits. The SQL client receives error 2013, `Lost connection to MySQL server during query`, after about 32.60 seconds. New SQL connections then fail with `Connection refused`.

This is a server panic rather than an OOM kill: cgroup `oom`, `oom_kill`, and `oom_group_kill` counters remained zero. No query cancellation or test memory guard was triggered for this 100,000-column reproduction.

### Expected behavior

Reject a schema that exceeds the supported column/sequence-number limit with a normal SQL error before committing catalog changes. A client statement must not terminate the storage service or the combined service process.

### Reproduction

Use a disposable local MatrixOne instance. This reproducer can terminate the server process. Adjust connection settings as necessary. No workload or concurrent DDL is required.

```sh
python -m pip install PyMySQL
```

```python
import pymysql

c = pymysql.connect(
    host="127.0.0.1", port=6001, user="root", password="111",
    autocommit=True, connect_timeout=5, read_timeout=120,
    write_timeout=120, ssl_disabled=True,
)
with c.cursor() as q:
    q.execute("CREATE DATABASE IF NOT EXISTS column_panic_repro")
    q.execute("USE column_panic_repro")
    columns = [
        f"c{i:07d} INT" + (" PRIMARY KEY" if i == 1 else "")
        for i in range(1, 100001)
    ]
    q.execute("CREATE TABLE wide_100000 (" + ",".join(columns) + ")")
```

The submitted statement was approximately 1.3 MB, below the observed `@@max_allowed_packet = 67108864`. All names are distinct and within identifier-length limits. The failure occurs during `CREATE TABLE`; no insert is needed.

### Panic stack

```text
panic: bad column idx 65533, table wide_100000

goroutine 844 [running]:
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/catalog.(*Schema).Finalize(...)
    pkg/vm/engine/tae/catalog/schema.go:962 +0x748
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/catalog.DefsToSchema(...)
    pkg/vm/engine/tae/catalog/model.go:150 +0x767
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/rpc.CreateRelation(...)
    pkg/vm/engine/tae/rpc/adaptors.go:42 +0x45
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/rpc.(*Handle).HandleCreateRelation(...)
    pkg/vm/engine/tae/rpc/handle.go:824 +0x292
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/rpc.(*Handle).handleRequests(...)
    pkg/vm/engine/tae/rpc/handle.go:318 +0x745
github.com/matrixorigin/matrixone/pkg/vm/engine/tae/rpc.(*Handle).HandleCommit(...)
    pkg/vm/engine/tae/rpc/handle.go:634 +0x32f
github.com/matrixorigin/matrixone/pkg/txn/storage/tae.(*taeStorage).Commit(...)
    pkg/txn/storage/tae/storage.go:186 +0xb1
github.com/matrixorigin/matrixone/pkg/txn/service.(*service).Commit(...)
    pkg/txn/service/service_cn_handler.go:278 +0xb42
github.com/matrixorigin/matrixone/pkg/tnservice.(*store).handleCommit(...)
    pkg/tnservice/store_rpc_handler.go:130 +0x19b
github.com/matrixorigin/matrixone/pkg/txn/rpc.executor.exec(...)
    pkg/txn/rpc/server.go:535 +0xec
github.com/matrixorigin/matrixone/pkg/txn/rpc.(*server).handleTxnRequest(...)
    pkg/txn/rpc/server.go:509 +0x334
github.com/matrixorigin/matrixone/pkg/common/stopper.(*Stopper).doRunCancelableTask.func1()
    pkg/common/stopper/stopper.go:281 +0x5b
created by github.com/matrixorigin/matrixone/pkg/common/stopper.(*Stopper).doRunCancelableTask in goroutine 584
    pkg/common/stopper/stopper.go:278 +0xba
```

### Environment and controls

- Linux; 4 CPU quota; 32 GiB cgroup memory limit.
- Single `mo-service -launch` process hosting LOG, TN, and CN; local DISK-V2 file services.
- Installed PyMySQL distribution 1.2.3 (`pymysql.__version__` reports 2.2.8); ordinary MySQL protocol connection with TLS disabled for this probe.
- Separate 1,000-column and 10,000-column tables passed creation, a full-row insert, `SELECT *` checking every column value/name/order, and an update/read of the last column.
- After restarting the server with the same data directory, the pre-crash 10,000-column row was readable with the expected first/middle/last values. The failed `wide_100000` table was absent from `information_schema.tables`.

### Relevant source / suspected cause

[`Schema.Finalize`](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/pkg/vm/engine/tae/catalog/schema.go#L960) explicitly panics when the column index reaches `objectio.SEQNUM_COMMITTS`.

[`SEQNUM_COMMITTS`](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/pkg/objectio/const.go#L32) is `math.MaxUint16 - 2`, i.e. 65,533. This storage invariant needs to be enforced as a checked schema limit, accounting for hidden columns, before this path is reached.

The planner defines `TableColumnCountLimit = 4096`, but the tested `CREATE TABLE` path accepted 10,000 columns and did not reject the 100,000-column schema before reaching storage.

### Follow-up: nearby boundary reproduction

The same isolated database was tested after recovery, using the same `INT` schema and first-column primary key:

| User columns | Observation |
|---|---|
| 65,530 | CREATE, full-row INSERT, SELECT of all columns with every value/name/order checked, last-column UPDATE and verification all passed. |
| 65,531 | CREATE and full-row INSERT succeeded, but reading the last column returned NULL instead of the inserted value 65,531. The two preceding columns returned 65,529 and 65,530 correctly. |
| 65,532 | CREATE and INSERT succeeded; last-column reads returned NULL and SELECT * failed the independent value oracle. A successful UPDATE of the last column still read back as NULL. |
| 65,533 | CREATE caused the same unhandled `panic: bad column idx 65533, table wide_65533`; the process exited and the client received 2013 after 19.79 seconds. No INSERT is required. |

Thus **65,533 columns is a confirmed smaller fatal reproducer for this primary-key schema**. Change `100001` to `65534`, and the table name to `wide_65533`, in the Python reproduction above.

The upper storage range has another symptom before this fatal threshold: after restarting, reading columns in the reserved range of the 65,532-column table returned SQL error 20101 with the recovered panic `bad path to read special column 65530` from `pkg/objectio/funcs.go:216`. This did not terminate the restarted service. The schema should be rejected before allowing writes or reads to use reserved sequence numbers.

[`SEQNUM_UPPER`](https://github.com/matrixorigin/matrixone/blob/2726fb419b3afa1db2686ae1b2aaca563d1ae214/pkg/objectio/const.go#L29) is 65,530, and multiple readers/logtail paths treat sequence numbers greater than or equal to it as special. The observed 65,531st user column uses zero-based sequence 65,530.

There is also inconsistent ALTER validation: an explicit-primary-key table created with 4,095 user columns rejected ADD COLUMN with 1117 `Too many columns`, while one created directly with 4,096 user columns accepted two additions (4,098 user columns verified in information_schema). The planner's ADD check compares the total column count for equality to 4,096 rather than enforcing a consistent upper bound. A coherent checked CREATE/ALTER limit must account for both storage reservations and hidden columns.

The one-million-column probe reached a client deadline and was then discontinued at the user's request; it is **not** evidence of a confirmed support limit or an additional fatal reproduction.
