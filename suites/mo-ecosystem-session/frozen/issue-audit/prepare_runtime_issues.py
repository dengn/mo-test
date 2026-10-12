import json
from pathlib import Path
B=Path(__file__).parent
env='''## 测试条件

- 日期：2026-10-11；Debian13 / Linux x86_64；本地独立 standalone MatrixOne（1 CN / 1 TN / 1 LogService）。
- 实际运行 SHA：`652c643666428f1c434e03369834f2a9bead7c27`；并未在最新 main 重新部署，验收需记录新的 SHA。本 issue 涉及路径未额外做最新 main 全链路 parity 核对。
- 对照：真实 MySQL8.4.11，PyMySQL1.2.3；本地独立 synthetic database，非业务数据。
- 本轮为完整工具进程与数据链路的正确性诊断，没有做长稳、吞吐或 exactly-once 认证。
- 以下SQL最小用例已在两个数据库实跑；本地 receipt 是证据来源名称，不是公开附件下载地址。

'''
link=lambda n,pr=False:f'https://github.com/matrixorigin/matrixone/{"pull" if pr else "issues"}/{n}'
items=[]
items.append({'key':'airbyte_load','title':'[Compatibility]: LOAD DATA SET NULLIF(@user_variable, ...) blocks Airbyte MySQL destination writes','labels':['kind/bug'],'body':env+'''## 真实链路与结果

Airbyte官方source-mysql3.53.7（image digest `sha256:5f2b26bb4338f5deb4930f7701bb8300214b35791a8ac9ac14a84ab6a42e26bf`）→真实RECORD/STATE协议→官方destination-mysql1.1.1（digest `sha256:e015a9c1ce38a8db54566ce7f69ff7805ef0e230d9faa7cb6d4800a1455f8026`），实际Docker连接器进程，非模拟数据。

本次使用本地协议runner执行官方check/discover/read/write，**没有部署Airbyte Kubernetes控制面/调度平台**。source binlog/游标测试与destination提交确认分别记录，不能把source STATE当成目标已提交。

destination.check 在MO/MySQL均SUCCEEDED；实际destination.write在MO bulk-load阶段失败，MySQL对照完成并返回带recordCount=3的STATE确认。目标命名空间已独立为airbyte_mo/airbyte_mysql，与源runtime_ecosystem.records隔离；早先同名目标改动源表的试跑已排除。

MO错误：
```text
20301 invalid input: the nullif func first param is not UnresolvedName form
io.airbyte.integrations.destination.mysql.MySQLSqlOperations.loadDataIntoTable
MySQLSqlOperations.kt:132/134
mysql-connector-java8.0.22
```

## 已运行最小复现

创建服务端/客户端可读取的CSV（LOCAL由客户端上传）：
```text
1,
2,hello
```

用PyMySQL `local_infile=True` 连接，执行：
```sql
CREATE DATABASE IF NOT EXISTS runtime_sql_repro;
USE runtime_sql_repro;
CREATE TABLE probe_load(id INT,v VARCHAR(20));
LOAD DATA LOCAL INFILE '/absolute/path/repro-load.csv'
INTO TABLE probe_load FIELDS TERMINATED BY ',' (id,@v)
SET v=NULLIF(@v,'');
SELECT * FROM probe_load ORDER BY id;
```

MySQL8.4.11：2行，`(1,NULL),(2,'hello')`。MO：20301拒绝。用户变量是MySQL合法LOAD SET表达式；仅接受UnresolvedName而拒绝VarExpr造成实际工具不可接入。

## 预期与验收

- [ ] 支持LOAD DATA列列表中的user variable在NULLIF及SET表达式中的使用，按每行输入求值。
- [ ] 空字符串→NULL、非空文本、显式NULL标记、Unicode与quoted CSV分别验证。
- [ ] 官方destination.check成功后write真正落表并返回持久化STATE；失败时不得错误确认source游标已提交。
- [ ] 先核对raw record accounting，再核对最终表。MySQL destination默认NUMBER/unsigned映射的precision/范围问题也在MySQL出现，属独立上游profile限制，不能随此SQL修复自动宣称保真。

## 关联与区别

- [本轮生态完整运行任务]('''+link(29848)+''')。
- [#5079]('''+link(5079)+''') 已关闭的LOAD SET NULL字符串feature使用列名，不覆盖本次@变量。
- [#6323]('''+link(6323)+''') 是SET目标列不存在检查；[#6466]('''+link(6466)+''') 是旧列名NULLIF格式化panic；触发路径不同。
- [#29842]('''+link(29842)+''') JSONLINE严格EOF静默丢行，属于另一文件入口正确性问题。

原始receipt：`isolated-standard-write-mo-1.jsonl`、`isolated-standard-write-mysql-1.jsonl`、`runtime-minimal-sql-result.json`。
'''} )
items.append({'key':'nifi_pk','title':'[Compatibility]: NiFi parameterized MySQL UPSERT rejects unchanged primary-key assignment','labels':['kind/bug'],'body':env+'''## 真实链路

ApacheNiFi2.4.0 / JDK21，真实REST配置的ExecuteSQLRecord→Avro→PutDatabaseRecord，MySQL dialect，StatementType=UPSERT，UpdateKeys=id，目标为MO。PutDatabaseRecord生成带参数的所有列赋值，包含`id = ?`，返回20313：

```text
unsupported DML: update primary key on duplicate
java.sql.BatchUpdateException
```

即使传入id等于冲突主键也失败，任务routing failure。普通字段upsert正常；`id=VALUES(id)`路径在本轮已通过，**不能把本问题称为#27911的相同VALUES(pk)复现**。

## 实跑最小SQL和对照

两个新建测试数据库执行相同SQL：
```sql
CREATE TABLE probe_pk(id INT PRIMARY KEY,v VARCHAR(20));
INSERT INTO probe_pk VALUES(1,'a');
-- 对照：两端均成功
INSERT INTO probe_pk VALUES(1,'a')
ON DUPLICATE KEY UPDATE id=VALUES(id),v=VALUES(v);
-- 实际NiFi绑定后对应形态：MySQL成功，MO20313拒绝
INSERT INTO probe_pk VALUES(1,'a')
ON DUPLICATE KEY UPDATE id=1,v='a';
-- 甚至无冲突的新主键，也在MO拒绝；MySQL插入成功
INSERT INTO probe_pk VALUES(2,'b')
ON DUPLICATE KEY UPDATE id=2,v='b';
```

MySQL8.4.11分别affected0、0、1；MO第一个affected0，后两个拒绝。此处无需复杂NiFi时间/decimal映射就能复现。

NiFi复现条件：真实DBCP使用Connector/J，MySQL dialect，目标有PK(id)，PutDatabaseRecord UPSERT/update key=id，输入Avro含id与普通列。普通ExecuteSQLRecord的record转换有独立类型限制，不能把它们算成本问题根因。后续显式SQL-outbox profile避开PK赋值并用于独立保真测试，不能据此判定默认UPSERT已修复。

## 预期与验收

- [ ] 当冲突定位的PK与入参PK相同，可接受无变化赋值；仍需明确真正改变PK/unique key的契约。
- [ ] `VALUES(pk)`、literal相同值、JDBC prepared parameter三种形态分别覆盖；不能只修VALUES模式。
- [ ] 空目标、重复主键、批量写、复合PK、NULL/约束异常与事务rollback有回归。
- [ ] 原始NiFi PutDatabaseRecord UPSERT成功并重放不增重复，不以手写SQL绕过作为原路径验收。

## 关联

- [#27911]('''+link(27911)+''') 已关闭的Flink `id=VALUES(id)` no-op问题，本轮该形态通过；参数/常量赋值仍失败。
- [#25102]('''+link(25102)+''') 已关闭的PK/unique upsert历史报告；本issue提供NiFi当前参数化触发条件和独立SQL对照。
- [#23306]('''+link(23306)+''') 旧FlinkCDC复合PK问题。
- [#29848]('''+link(29848)+''') 本轮完整运行认证任务。

原始receipt：`nifi-native-result.json`、`pk-upsert-retest-result.json`，以及mo-service实际绑定后的SQL trace。
'''} )
items.append({'key':'connect_alter','title':'[Compatibility]: Parenthesized ALTER ADD COLUMN blocks Debezium JDBC schema evolution','labels':['kind/bug'],'body':env+'''## 完整运行链路与触发

MySQL8.4.11 ROW/FULL binlog→Kafka3.9.1 KRaft→Connectdistributed worker→DebeziumMySQLsource3.1.2.Final→DebeziumJDBCsink3.1.2.Final→MO。sink使用`schema.evolution=basic`、PKupsert和delete.enabled=true，source使用adaptive_time_microseconds。

宽类型快照、insert/update/物理delete、微秒读回已通过。源执行新增nullable列并更新后，sink自动发出的语句为：

```sql
ALTER TABLE kc_exact_records ADD COLUMN ( added_tag longtext NULL)
```

MO报1064语法错误，sink task FAILED，source仍RUNNING。仅看connector顶层状态会漏掉实际task失败。已有目标行仍存在，但新列/后续变更无法消费。

## 实跑最小SQL

MO与真实MySQL8.4.11分别运行：
```sql
CREATE TABLE probe_add(id INT);
ALTER TABLE probe_add ADD COLUMN (added_tag LONGTEXT NULL);
```

MySQL接受；MO报1064，错误位置在`(added_tag LONGTEXT NULL)`。没有其他FK/index/copy-mode条件。

## 原始过程、适配与恢复

1. 三行宽类型源表：INT64/UINT64、大decimal、binary、中文emoji、DATETIME6微秒、JSON、NULL。
2. snapshot精确；更新/新增/删除也精确。
3. source `ALTER TABLE records ADD COLUMN added_tag VARCHAR(100) NULL`，随后更新id1新列为中文；自动schema evolution失败，source/sink逐字段比对失败。
4. 手工在MO使用无括号`ALTER TABLE kc_exact_records ADD COLUMN added_tag LONGTEXT NULL`，restart failed sink task。
5. 同一offset/config/status Kafka topics保留；worker停止期间继续source update/delete/insert，再重启worker，原checkpoint补追并收敛，PK总数=去重数。

步骤4是明确的DDL适配，不能据此宣称自动evolution原路径通过。本轮worker恢复是有序stop/restart，未认证SIGKILL/系统断电/跨系统exactly-once。

## 预期与验收

- [ ] 支持MySQL合法的括号列定义列表，单列/多列、nullable/default/不同类型分别覆盖。
- [ ] 原DebeziumJDBC basic evolution无需手工DDL即可新增列、消费新字段并保持旧行。
- [ ] 保存connector与task状态、精确SQL/error、源目标schema和值；恢复后检查checkpoint/重复/漏行。
- [ ] 列重命名、删除和类型变更按独立支持契约验证；basic ADD通过不能推出DROP/RENAME支持。

## 关联与区别

- [#29848]('''+link(29848)+''') 本轮完整运行与恢复认证；[#27746]('''+link(27746)+''') 既有MySQL生态/Flink资格认证。
- [#28052]('''+link(28052)+''') COPY ALTER组合ADD COLUMN/INDEX问题；[#28995]('''+link(28995)+''') ADD COLUMN/FK组合问题；这里仅单列括号语法，不依赖组合DDL。

原始receipt：`kafka-runtime-result.json`、`runtime-minimal-sql-result.json`、connector failure trace。
'''} )
(B/'runtime-new-issue-drafts.json').write_text(json.dumps(items,ensure_ascii=False,indent=2))
print([(i['key'],len(i['body'])) for i in items])
