# MatrixOne TTL capability assessment

Checked on 2026-10-13 (Asia/Shanghai). **Current `main` does not provide native business-row/table TTL. SQL tasks can implement periodic deletion.** This is a capability assessment, not a scalability or long-duration cleanup benchmark.

## Evidence and scope

- Runtime built from `fa7cc1d9b38e3324572a4efc5617033522de0cbf`; `git_version()` returned `fa7cc1d9`. The later observed main `3e50e1b32d8da61bbbf70c89989fb08b671809de` has identical TTL-relevant parser/DDL/catalog/task/GC sources. See `main-source-verification.json`; the later commit was not rebuilt.
- [Native table TTL request #24552](https://github.com/matrixorigin/matrixone/issues/24552) remains open. Its comment reports ongoing testing and a planned future merge; it is not evidence of availability in main.
- [Parser PR #24754](https://github.com/matrixorigin/matrixone/pull/24754) and [planner PR #24779](https://github.com/matrixorigin/matrixone/pull/24779) targeted `4.0-dev`, were closed, and have `merged_at=null`. Their proposed TiDB-like `TTL`, `TTL_ENABLE`, and `TTL_JOB_INTERVAL` syntax is absent from the inspected main parser. Closed does not mean merged.
- [Lifecycle/archive PR #26655](https://github.com/matrixorigin/matrixone/pull/26655), targeting main, is open and draft. It includes TTL retirement and archival/restoration but has not been merged. Its claimed branch tests cannot establish main support.
- The official [CREATE TABLE handbook](https://github.com/matrixorigin/matrixone-doc/blob/9d30c619ef3a8235bfa3d1490c1843cdbca6f1b7/docs/MatrixOne/Reference/SQL-Reference/Data-Definition-Language/create-table.md) does not define native TTL. The [CREATE PITR handbook](https://github.com/matrixorigin/matrixone-doc/blob/9d30c619ef3a8235bfa3d1490c1843cdbca6f1b7/docs/MatrixOne/Reference/SQL-Reference/Data-Definition-Language/create-pitr.md) defines a recovery-history window; this does not expire current business rows. Public docs URLs tried redirected to a different product landing page, so no landing-page HTTP 200 is treated as a retrieved SQL reference.

## Runtime verification

Run `MO_PORT=6013 /workspace/mo-gis-app-projects/python-env/bin/python probe.py`. Connection defaults are disposable local test credentials; environment variables can override them. The probe owns only database `mo_ttl_capability_20261013` and drops its own scheduled task when done.

| Capability | Result |
|---|---|
| Native `CREATE TABLE ... TTL=...` and `TTL_ENABLE` options | Syntax rejected |
| `WITH (ttl=...)` | Syntax rejected |
| MySQL `CREATE EVENT` scheduling | Syntax rejected |
| Generic `PROPERTIES('ttl'=..., 'ttl_enable'=...)` | Accepted as metadata, but expired row remained; acceptance does not implement TTL |
| SQL task scheduled `DELETE ... WHERE expires_at <= NOW()` | Verified a `SCHEDULED/SUCCESS` run deleting two expired rows |
| Future expiration / NULL expiration | Both retained |
| Suspend task | Newly inserted expired row retained |
| Explicit `EXECUTE TASK` | Expired row deleted; future/NULL rows retained |
| Connection health after probes | `SELECT git_version(),1` succeeded |

Inputs, SQL responses, timing, and assertions are in `probe.py`, `runtime-results.json`, `probe.log`, and `assertions.json`. There are six unsupported-syntax probes and four behavioral assertions; repeated polling is not counted as additional independent test cases. No panic was observed in this focused probe.

## Usable alternative on the tested main

```sql
CREATE TABLE ttl_events (
  id BIGINT PRIMARY KEY,
  expires_at DATETIME NULL,
  payload JSON,
  INDEX idx_expiry (expires_at)
);

-- Six cron fields: second minute hour day month weekday; every 5 minutes.
CREATE TASK cleanup_ttl_events
  SCHEDULE '0 */5 * * * *'
  TIMEZONE 'UTC'
  AS BEGIN
    DELETE FROM ttl_events WHERE expires_at <= NOW();
  END;

SHOW TASK RUNS FOR cleanup_ttl_events LIMIT 10;
ALTER TASK cleanup_ttl_events SUSPEND;
ALTER TASK cleanup_ttl_events RESUME;
```

The runtime probe used an accelerated `*/2 * * * * *` schedule. A SQL task is asynchronous: scheduler discovery, execution queues, workload, failures and outages can delay cleanup. It does not guarantee disappearance exactly at the expiration timestamp. To hide expired data at read time, consistently query through `WHERE expires_at > NOW() OR expires_at IS NULL`, or an appropriately defined view. Use a consistent UTC expiration convention and check session/task execution timezone for TIMESTAMP values; this probe used UTC and DATETIME values.

For heavy log/trace/trajectory retention, periodic DELETE generates ordinary transactional work and index maintenance. Benchmark cleanup cost together with ingestion and GIS/vector/full-text indexes, and use bounded batches where supported. This probe did not certify the performance of deleting millions of rows or partition lifecycle management. SQL deletion also does not mean immediate physical object removal: active transactions, snapshots/PITR/branches and GC can retain historical data. Internal cache, token, lease and GC-protection TTL settings are separate from business-data expiry.

**Recommendation:** use SQL tasks or an external scheduler plus query-time expiration filters for current deployments; track #24552/#26655 if native TTL or archive-based retention is required.
