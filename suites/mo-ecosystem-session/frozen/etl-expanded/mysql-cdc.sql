SET 'execution.checkpointing.interval'='2 s';
SET 'execution.checkpointing.mode'='EXACTLY_ONCE';
SET 'restart-strategy.type'='fixed-delay';
SET 'restart-strategy.fixed-delay.attempts'='5';
SET 'restart-strategy.fixed-delay.delay'='2 s';
CREATE TABLE mysql_source (
 id BIGINT, name STRING, amount DECIMAL(18,2), updated_at TIMESTAMP(3), PRIMARY KEY(id) NOT ENFORCED
) WITH (
 'connector'='mysql-cdc','hostname'='mo-etl-mysql','port'='3306',
 'username'='root','password'='etl-local','database-name'='etl_source','table-name'='accounts',
 'server-id'='5500-5504','server-time-zone'='UTC','scan.startup.mode'='initial',
 'scan.incremental.snapshot.enabled'='true'
);
CREATE TABLE mo_sink (
 id BIGINT, name STRING, amount DECIMAL(18,2), updated_at TIMESTAMP(3), PRIMARY KEY(id) NOT ENFORCED
) WITH (
 'connector'='jdbc','url'='jdbc:mysql://mo-host:6001/etl_mysql_cdc?useSSL=false&rewriteBatchedStatements=true',
 'table-name'='accounts','driver'='com.mysql.cj.jdbc.Driver','username'='root','password'='111',
 'sink.buffer-flush.max-rows'='1','sink.buffer-flush.interval'='1 s'
);
INSERT INTO mo_sink SELECT * FROM mysql_source;
