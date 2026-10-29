# MatrixOne 数据生态、ETL、故障恢复与重载测试

本目录汇集本会话 **13 个材料目录**的用例源码、合成输入、SQL、执行日志、失败记录、独立回读和问题关联。它与仓库已有的数据科学及边界/混沌批次分别计数。

## 最新续跑检查点

最新主计划已完成 **32,431/160,000**，剩余 **127,569**；PETL 5,000、pandas 2,431。另有 Iceberg 读取补测 5,000（4,920 通过、80 原生库过滤失败），独立计数。见 [续跑检查点](continuation/20261012-windowed/README.md)。以下表格和 catalog 保留最初发布时的历史快照口径。

## 用例计数与真实状态

|主批次|计划|实际唯一执行记录|记录状态|计数口径|
|---|---:|---:|---|---|
|五种 ETL 路径|10,000|10,000|配置条件下通过|5 路径 × 20 类型 × 5 场景 × 10 种子 × 2 端点|
|五种编排/连接器路径|10,000|10,000|配置条件下通过|Airflow、DolphinScheduler、dbt、Airbyte、Fivetran SDK，各 2,000|
|32 工具重载扩展|160,000|27,559|已执行部分通过；其余 132,441 未执行|PETL 2,559；ConnectorX、Ibis、ODBC、MO Python SDK、JDBC 各 5,000|
|主批次执行记录合计|—|47,559|保留原生失败和配置条件|包括 MySQL 对照；不能解释为 47,559 个 MO 原生认证|

主批次 `case` 是有独立 ID 的参数化场景/行集断言，包含类型、场景、种子、端点；不是一个独立 DAG、容错事件或不同算法。两端点分别计数。重载读取组使用 **32–256 虚拟行的真实 SQL 查询**，不是每个 case 都写入该数量的物理行。

初始预检、原生 Airbyte 失败、SDK 精度修正前记录、重试与补测另存；配置后的主记录不覆盖它们。早期探针、吞吐和故障测试粒度不同，不混入此分母。EOS 第六轮有 **30 个检查：17 个限定条件下正例、13 个预期反例**，保留 ledger、checkpoint、非幂等效果、ACK 丢失、重平衡和僵尸写入者证据。

最新 160,000 计划中，26 类工具的完整重载链路尚未完成。部分工具已有早期原生测试，但不能据此补算每工具 5,000。`catalog/heavy-planned.jsonl.gz` 明确标记计划与运行器实现状态；读取组使用自己的 10 种读取场景。最终状态以 `heavy-status.json` 和执行索引为准。

## 材料结构

* `frozen/<batch>/`：可浏览的冻结 Python、SQL、Shell 用例源码；原执行路径、依赖和默认本地账号保留。
* `archives/<batch>.zip`：13 个普通 Git 归档，包含全部选入源码、文本 fixture、记录、日志和配置。没有外部网盘或 LFS 依赖。
* `source-manifest.json`：每个成员的原文件 SHA256、发布 SHA256、归档路径和可浏览文件路径；也列出选入范围及排除项。
* `archive-manifest.json`、`artifact-manifest.json`：归档及全部新增发布文件的大小与 SHA256。
* `catalog/executed-main.jsonl.gz`：47,559 条索引，精确指向原始记录成员及行号。
* `catalog/heavy-planned.jsonl.gz`：160,000 条计划索引，不能当成执行结果。
* `replay/heavy/`：核心写入及五种原生读取 API 的迁移入口，连接/输出路径由环境变量配置。
* `issues.json`：38 个关联问题的编号、标题、链接与最小复现定位；`issue-snapshots/` 保存 19 个本会话报告的完整发布说明/SQL/测试条件。
* `migration-validation.json`：本次打包/入口迁移验证，独立于历史主批次计数。

运行中 MO/MySQL/MinIO 数据目录、第三方源码 checkout、服务二进制、JAR、安装包、虚拟环境、缓存、私钥和本地认证会话不在包中；原生组件通过官方发行包重新部署。旧的重复 ZIP 不再次嵌套打包。Fivetran 本地 DuckDB 由官方 SDK 重新生成，原始精度失败的 JSON/日志已保留。重载的 201,945 行合成 MySQL 归档及校验/恢复源码保存在 `heavy-5000.zip` 中，它不是新的 case 数。

所有已选入源码/记录的对应关系在清单中可检查；这是一份 **用例与证据包**，不是可直接恢复整个运行环境的镜像。源码文件数、归档成员数和压缩大小由清单与校验工具读取，避免手填不一致。

## 校验与恢复

从仓库根目录执行，Python 3.12+；仅校验/恢复使用标准库：

```bash
python3 tools/ecosystem_materialize.py --verify-only
python3 tools/ecosystem_materialize.py --output work/ecosystem-session
# 也可以只恢复一个材料目录
python3 tools/ecosystem_materialize.py --batch eos-6 --output work/ecosystem-eos
```

工具校验全部文件/ZIP/成员 SHA256、CRC、重复成员、路径、冻结源码一致性，独立核对主索引与源记录的 ID/状态/类型/场景/种子，以及 32 × 5,000 计划唯一性。目标目录存在时拒绝覆盖；恢复不执行测试代码，不启动或停止服务。全部解压建议留出 **500 MiB 以上**；完整原生运行需要远多于此的磁盘。

## 可配置的重载重跑入口

在专用合成数据实例中运行。MO 和 MySQL 可以在不同主机或相同端口；记录中的 6001/13306 是保持历史 ID 的**逻辑端点角色**，实际连接使用环境变量。当前迁移入口连接设置为本地测试用的非 TLS 模式。

```bash
python3 -m venv work/ecosystem-venv
work/ecosystem-venv/bin/pip install -r suites/mo-ecosystem-session/replay/heavy/requirements-core.txt
export MO_HOST=127.0.0.1 MO_PORT=6001 MO_USER=root
export MYSQL_HOST=127.0.0.1 MYSQL_PORT=13306 MYSQL_USER=root
# MO_PASSWORD、MYSQL_PASSWORD 从当前测试环境注入；不提交实际连接密钥。
export MO_TEST_DATABASE=mo_ecosystem_my_unique_run
export MO_CASE_OUTPUT="$PWD/work/ecosystem-my-unique-run"
work/ecosystem-venv/bin/python suites/mo-ecosystem-session/replay/heavy/init.py
work/ecosystem-venv/bin/python suites/mo-ecosystem-session/replay/heavy/run_core.py --route petl --preflight --limit 200 --workers 2
work/ecosystem-venv/bin/python suites/mo-ecosystem-session/replay/heavy/run_core.py --route petl --limit 5000 --workers 4
```

核心实际路径为 `petl`、`polars`、`dask`、`duckdb_parquet_bridge`、`arrow_ipc_bridge`，另有 `pandas`、`sqlalchemy`、`pymysql`、`mysql_connector` 入口。后四者的 5,000 重载运行尚未完成；有入口不等于认证。只写入自身数据库，数据库名必须符合 `mo_ecosystem_<run_id>`。初始化拒绝接管没有匹配所有权标记的已有库。无服务 kill、数据目录删除、S3 桶清理或自动数据库 DROP。默认磁盘下限 600 MiB，容量不足会中止。

相同输出文件按独立 case ID 跳过已经记下的结果；初始失败会保留，不被重跑悄悄改成成功。换新输出目录可以生成新的重跑记录。对比 preflight 与主测试请分别读取 `*-preflight.jsonl` 与主 `.jsonl`。`--limit` 是每条路径的实际执行上限；完整重载应为 5,000。

### 原生读取路径

```bash
work/ecosystem-venv/bin/pip install -r suites/mo-ecosystem-session/replay/heavy/requirements-readers.txt
work/ecosystem-venv/bin/python suites/mo-ecosystem-session/replay/heavy/seed_readers.py
work/ecosystem-venv/bin/python suites/mo-ecosystem-session/replay/heavy/read_tools.py --tool connectorx --limit 5000 --workers 4
```

工具选项是 `connectorx`、`ibis`、`odbc`、`matrixone_sdk`、`jdbc`。ODBC 设置 `MO_ODBC_DRIVER`，按官方驱动安装 `unixODBC`/动态库；历史仅测试 Unicode 驱动。JDBC 设置 `MO_JDBC_JAR` 指向 Connector/J 8.4.0，并安装 JVM。MO SDK 安装对应版本，或设置 `MO_SDK_PATH` 指向固定源码的 `clients/python`。所需二进制不内嵌。seed 步骤通过真实 PETL 写入 50 组源数据/1,600 行并核验；是准备过程，不新增 5,000 case。

读取组包括分页、并行分区、NULL 过滤/计数、自连接、重放 UNION、窗口 TopK、复用连接上下文、分批读取。精确数值/日期/时间使用明确 CAST 文本，二进制用 HEX 后解码；这验证真实 API 和该表示约定，不能推导默认类型推断全部正确、写入恢复或 native exactly-once。

### 关键保真和适配约定

* 20 个基础类型加 DECIMAL(65,30)、ENUM、SET、BIT(64)、UUID CHAR(36)；SQL NULL 与 JSON null 区分。
* DECIMAL(65,30) 经过部分引擎时用精确字符串适配，不冒充原生 Decimal65；工作线程精度明确设置为 100。
* FLOAT32 以 6 位有效数字验收；CHAR 按尾空格裁剪约定；不能称为浮点位级/字符串字节级完全保真。
* PETL 使用 ANSI_QUOTES；Dask 关闭自动字符串转换并显式绑定类型；Polars TIME 用精确 SQL 时间字符串；DuckDB 负 TIME 用 int64 微秒 Parquet 表示。
* DuckDB/Arrow 路径为原生文件处理加显式 SQL sink；不是官方 MO connector。
* 删除/合并/DDL/重放涉及明确 SQL 效果适配。MO ENUM/SET JOIN UPDATE 原生失败 #29923 保留；配置路径用单表绑定更新。
* `replay_merge` 是常量赋值的幂等适配；`duplicate_rollback_retry` 是 staging 原生输入失败加显式效果事务回滚；均不能代替跨系统非幂等 EOS。

## 编排、连接器和早期轮次重放

原生服务测试按归档中的代码与固定版本在**新的运行副本**部署。`frozen` 是历史证据，不能直接当作当前生产环境脚本；先恢复，再调整专用实例、端口、服务路径、进程归属及凭据。

|材料目录|主要路径/场景|定位与重放要点|
|---|---|---|
|path-verification|Spark、Trino、Iceberg、Arrow、ODBC、TLS、图相关 SQL/接口探针|顶层 probe/retest 源码；部分接口仅探测，不计为已运行图引擎|
|etl-expanded|批处理、DataX、Spark JDBC、Flink CDC、dbt、DuckDB、压缩/S3|保留 dbt 原生和适配项目；替换外部发行包位置|
|type-expanded|宽类型、JSONLINE EOF、Decimal、ENUM/SET、Singer、SeaTunnel|顶层类型输入、source/sink 原始记录、失败重测|
|runtime-expanded|Kafka Connect/Debezium、NiFi、官方 Airbyte 协议|部署与运行/回读源码，Airbyte 配置和记录|
|runtime-expanded-2|CDC DDL/删除、NiFi 拒绝、Airbyte 扩展|单独保留第二轮，不覆盖初始结果|
|certification-3|吞吐、短时稳定性、typed fidelity、EOS|执行条件/资源与 native/adapter 结果分开|
|ecosystem-4|dlt、Redpanda Connect、Confluent JDBC、PostgreSQL 类型|原生与别名适配 SQL、异常与恢复|
|pressure-5|百万行、混合负载、连接取消、热点事务、崩溃恢复、JDBC A/B|只在隔离实例重放故障/压力，固定资源约束|
|eos-6|ledger/effect/checkpoint、ACK 丢失、重平衡、fencing、保留期缺口|30 检查含 13 反例；自建效果协议，不是官方连接器 EOS|
|etl-10000|五种原生/文件桥 ETL 路径|`matrix.py`、`prepare.py`、`run_parallel.py`，原运行 fixtures 和主记录|
|etl-orchestrators-10000|下表五种原生组件|`generate.py` 准备 fixtures，按原项目隔离安装依赖|
|heavy-5000|25 类型 × 10 场景的重载计划/已运行子集|优先使用 `replay/heavy` 可配置入口；冻结原始错误/修正快照保留|
|issue-audit|源码审查、issue 复现条件及关联|问题草稿/发布记录保留；不要再次批量创建 issue|

|组件|实际已测试链路|边界及关键源码|
|---|---|---|
|Airflow 3.3.2 / MySQL provider 6.7.0|原生 API/scheduler/DAG processor/LocalExecutor，MySqlHook|`airflow-home/dags/matrixone_hook.py`、`worker.py`；2 task 而非 2,000 DAG；真实 task retry|
|DolphinScheduler 3.4.2|原生 master/worker/API/H2，Shell→显式 PyMySQL sink；补测原生 MYSQL/SQL task|`submit_dolphin.py`、`submit_dolphin_sql.py`；不能把 2,000 Shell 断言写成 2,000 JDBC 类型认证|
|dbt-core 1.7.20 / dbt-mysql 1.7.0|20 table model + 20 key test/端点，全量回读|`prepare_dbt.py`、`run_dbt.py`、`dbt-project`；不含原生增量/删除 CDC/EOS|
|Airbyte source-mysql 3.53.7 / destination-mysql 1.1.1|官方 Docker 协议 runner；8110 outbox 事件，MySQL native sink|`run_airbyte.py`；MO native write 被 #29849 阻断、0 STATE ACK；`airbyte_adapter.py` 的成功是显式 SQL sink，不覆盖原生失败；未跑完整 Airbyte 平台|
|Fivetran Connector SDK 2.12.1 / tester 2.26.0908.001|**官方 SDK 本地链路**、真实 upsert/update/delete/checkpoint、MO/MySQL 为源、本地 DuckDB 为目的|`fivetran-project/connector.py`、`fivetran_phase.py`、`prepare_fivetran.py`；每阶段新进程，保留精度 28→80 修正和恢复；字符串信封，不是所有类型原生映射或托管 SaaS|

Airflow、dbt、Fivetran 依赖分别使用不同虚拟环境，避免 protobuf 等依赖冲突。Fivetran 重跑以 `fivetran_phase.py` 的新进程阶段为准；早期 `run_fivetran.py` 同进程复用失败也是保留的负面证据。仅调用 worker.py 不能认证 Airflow 或 DolphinScheduler 完整链路。

旧生命周期脚本（例如 `start.py`、`fresh_mo.py`、`cleanup.py`、`archive_stop.py`）只保留供审查，**不要按原绝对路径直接执行**。本次恢复/迁移工具不调用它们。原重载“新命名空间”配置未实际生效，正确说明在 `fresh-mo-resume-petl.json` 中；不能把该尝试写成已验证 fresh namespace。

## 版本、问题与验收限制

固定执行 MO 提交：`652c643666428f1c434e03369834f2a9bead7c27`；二进制 SHA256：`7fcb538dd5465331b9e250214f74fb75b4b9ca33960fcd48280fb7d4666f1a67`。不是当前 main 的认证。机器为共享 4 CPU quota / 16 GiB，历史磁盘不足导致重载暂停；未完整完成 24–72h 长稳、生产多节点 HA、所有组件的跨系统 exactly-once。

总追踪：[matrixone #29848](https://github.com/matrixorigin/matrixone/issues/29848)。重点包括 [P0 跨库 EXISTS 静默误删 #29876](https://github.com/matrixorigin/matrixone/issues/29876)、[原生 Airbyte LOAD DATA #29849](https://github.com/matrixorigin/matrixone/issues/29849)、[NiFi PK 更新 #29850](https://github.com/matrixorigin/matrixone/issues/29850)、[Debezium DDL #29851](https://github.com/matrixorigin/matrixone/issues/29851)、[效果协议/EOS #29857](https://github.com/matrixorigin/matrixone/issues/29857)、[dlt 窗口排序 #29877](https://github.com/matrixorigin/matrixone/issues/29877)、[ENUM/SET JOIN UPDATE #29923](https://github.com/matrixorigin/matrixone/issues/29923)。完整关联在 `issues.json`。

`replay/heavy/enum_repro.py` / `enum_workarounds.py` 能在自有专用库重现 #29923 的原生与对照结果；`load_repro.py` 重现 #29849，MySQL 对照要求服务端 `local_infile=ON`。运行器不自动修改服务端全局设置。这些复现记录异常而非假定所有语句都必须成功。所有通过结果都仅适用于对应输入、适配、资源和验收条件。
