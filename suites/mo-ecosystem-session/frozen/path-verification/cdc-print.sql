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
CREATE TABLE print_sink(id BIGINT,name STRING,amount DECIMAL(18,2),updated_at TIMESTAMP(3)) WITH ('connector'='print');
INSERT INTO print_sink SELECT * FROM pg_source;
