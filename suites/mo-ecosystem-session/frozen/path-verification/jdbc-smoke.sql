SET 'execution.checkpointing.interval' = '2s';
SET 'execution.checkpointing.mode' = 'EXACTLY_ONCE';
SET 'pipeline.operator-chaining.enabled' = 'false';
SET 'restart-strategy.type' = 'fixed-delay';
SET 'restart-strategy.fixed-delay.attempts' = '5';
SET 'restart-strategy.fixed-delay.delay' = '2s';
CREATE TABLE pg_source (
 id BIGINT, name STRING, amount DECIMAL(18,2), updated_at TIMESTAMP(3),
 PRIMARY KEY (id) NOT ENFORCED
) WITH (
 'connector' = 'postgres-cdc',
 'hostname' = 'mo-audit-pg', 'port' = '5432',
 'username' = 'audit', 'password' = 'audit-local',
 'database-name' = 'audit', 'schema-name' = 'public', 'table-name' = 'accounts',
 'slot.name' = 'mo_audit_slot', 'decoding.plugin.name' = 'pgoutput',
 'scan.incremental.snapshot.enabled' = 'false'
);
CREATE TABLE mo_sink (
 id BIGINT, name STRING, amount DECIMAL(18,2), updated_at TIMESTAMP(3),
 PRIMARY KEY (id) NOT ENFORCED
) WITH (
 'connector' = 'jdbc', 'url' = 'jdbc:mysql://mo-host:6001/cdc_audit?useSSL=false&rewriteBatchedStatements=true',
 'table-name' = 'accounts', 'username' = 'root', 'password' = '111',
 'driver' = 'com.mysql.cj.jdbc.Driver',
 'sink.buffer-flush.max-rows' = '1', 'sink.buffer-flush.interval' = '1s'
);
INSERT INTO mo_sink VALUES(991,'jdbc smoke',CAST(1.23 AS DECIMAL(18,2)),TIMESTAMP '2026-10-10 12:00:00.123');
