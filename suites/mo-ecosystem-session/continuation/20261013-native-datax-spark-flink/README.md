# DataX / Spark / Flink native validation, 2026-10-13

This is an additional **122 executed case attempts**, with **90 passes / 32 failures**, preserved separately from earlier main-plan snapshots. Installation, compilation and preflight attempts are not cases. This package does not imply the remaining 5,000-case tool plans have completed.

| Tool | Attempts | Pass | Fail | Scope |
|---|---:|---:|---:|---|
| DataX | 66 | 38 | 28 | Java 21/Groovy failures retained; Java 8 pilot; real table scans; temporal VARCHAR staging + SQL conversion |
| Spark | 44 | 40 | 4 | PySpark native append; actual JDBC reader/two partitions; raw types and explicit value adapters |
| Flink | 12 | 12 | 0 | Actual MySQL snapshot/binlog, two JDBC sinks, updates/deletes, primary-key changes, fixed projection across ADD COLUMN, checkpoint restoration and rolled-back source transaction |

MatrixOne commit: `652c643666428f1c434e03369834f2a9bead7c27`. Source/control: isolated MySQL 8.4, localhost23306; MatrixOne localhost16001. DataX used bundled mysqlreader/mysqlwriter + Connector/J5.1.47 + Groovy2.1.9 with Java8 (failed Java21 attempts remain). Spark used PySpark3.5.7/Java17/ConnectorJ8.4.0. Flink used1.20.2/MySQLCDC3.6.0-1.20/JDBC3.3.0-1.20/ConnectorJ8.4.0/Java17.

## Evidence and failures

`evidence.zip` includes122 individual results, original typed inputs/expected-value oracles,22 fully verified SQL window archives and receipts, component provenance, the minimal Groovy failure/success probe, and checkpoint/source-binlog receipts. ZIP and all contained files were read back and SHA256 verified. Generated expected values were checked against immutable recorded hashes whenever available. Java21 failures occurred before expected hashes were recorded; their deterministic fixture reconstruction is explicitly marked. MySQL's canonical JSON key ordering is retained when reconstructing the recorded CDC hash.

- DataX Java21 + Groovy2.1.9:20 failures at initialization, against both destinations; minimal probe reports inaccessible `Object.finalize`. Java8:20 additional tinyint append cases pass.
- DataX real scans:14/22 pass. DATETIME native `.123456` becomes `.123000`; source CAST text directly into a temporal destination becomes `.000000`. TIME default binding rejects negative/extended values, including dirty records and retained partial effects. The same failures occur with the MySQL destination. Four separate VARCHAR staging + SQL CAST cases all pass, preserving year1000/9999, negative microseconds and ±838-hour TIME.
- Spark real reads/writes:20/24 pass. Native DECIMAL(65,30) and extended TIME default source conversion fail for both sinks; explicit text conversion passes. This round's native DATETIME(6) values pass.
- Flink:Job `01c5f3cd5d6ffecc6ae85cd28de42119`, restored checkpoint3 (`is_savepoint=false`). Both sinks have64/80/80/80/73/73 rows across the six phases, with complete fresh-connection all-field checks. The final job was submitted through native TableEnvironment.executeSql. Cropped-installation/embedded SQL Gateway preflights remain failures and do not count as CDC cases. This does not certify SQL Client submission in this round.

Flink ordinary JDBC remains **at-least-once with idempotent primary-key final effects**. Flink `EXACTLY_ONCE` state mode is not XA or external database exactly-once. ADD COLUMN qualifies the existing fixed projection, not new-field propagation. Manual older-checkpoint replay, binlog expiry, non-idempotent effects, throughput, long soak, HA and distributed scale are unqualified.

The measured environment used temporary filesystem storage, serialized tools, at most2 case workers,20-case main-plan windows, an explicitly approved5GiB then6GiB used-space cap, at least2GiB free and3GiB estimated memory headroom. All old databases, directories and buckets were retained. Only newly registered temporary SQL tables were recycled after typed archive, archive readback, original oracle checks and fresh SQL reread. These results are not disk throughput certification.

## Reproduce in a fresh isolated Linux environment

`frozen-source/` preserves end-of-round runner sources and the shared deterministic fixture/archive implementation. `source-manifest.json` records file SHA256. It is reviewable test material, not a deployment of historical services or inherited permission to clean data.

The optional preparation helper relocates these sources and handles environment-supplied runtime paths. It was Python-compiled only; it has **zero additional executed cases**. It prepares the62 expanded cases (22DataX scans +24Spark scans +4temporal-stage +12CDC); the60 pilot/JVM diagnostic attempts remain in the frozen scripts/results/oracles for independent reproduction.

1. Install the pinned Python dependencies using `requirements-replay.txt` in an isolated environment. Provision independent test MatrixOne/MySQL servers at localhost16001/23306. MySQL must already have binlog=ON, ROW/FULL and appropriate replication permissions; this package does not modify server-wide settings or launch SQL services.
2. Set `DATAX_HOME`, `JAVA8_HOME`, `JAVA17_HOME`, `MO_JDBC_JAR`, `FLINK_MYSQL_CDC_JAR`, `FLINK_JDBC_JAR` and `FLINK_HOME` to verified artifacts. Use a separate, complete Flink1.20.2 installation and ensure its owned cluster ports18081/18123 are free. Read the original evidence inventory to match versions and checksums.
3. Set `MO_PASSWORD` and `MYSQL_PASSWORD` privately, `MO_PORT=16001`, `MYSQL_PORT=23306`, and a fresh `MO_TEST_DATABASE=mo_ecosystem_native_<unique_lowercase_suffix>`. Set `MO_NATIVE_REPLAY_ROOT` to a nonexistent directory on a suitable separate test filesystem. Existing replay workspaces/databases are refused.
4. Explicitly set `MO_NATIVE_REPLAY_ACCEPT_LIMITS=1` to accept the6GiB used-filesystem cap,2GiB free floor and3GiB cgroup memory-headroom check. Set `MO_CASE_MIN_FREE_MIB=2048` and `MO_CASE_OUTPUT=$MO_NATIVE_REPLAY_ROOT/results`. Keep credentials and generated job files private (`umask077`). No database cleanup is enabled by default; optionally set `MO_NATIVE_REPLAY_REUSE=1` before preparation for verified newly registered tables only.
5. Run `python prepare_replay.py`, then `python bootstrap.py`. Bootstrap refuses existing database names and creates only new synthetic databases with ownership markers.
6. Run sequentially: `python "$MO_NATIVE_REPLAY_ROOT/native-dsf/actual_batch.py" dataxscan`, then `sparkscan`, then `datax_temporal_stage.py`, then `flink_cdc.py`. The last runner starts/stops only its own Flink processes, preserves checkpoints and records actual native source/sink effects.

New replay results are separate from this evidence. Do not overwrite failed original cases with successful adapters or count supplied fixtures as executed cases. Keep failed effects, fresh all-field hashes, source positions and checkpoint restoration evidence.
