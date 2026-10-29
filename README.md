# mo-test

本会话八批 MatrixOne 数据科学与复杂分析测试：**360,000 个主批次 case**，包括失败 case、原始 SQL/参数/预期结果、Spark/Flink 补测、复杂业务流程、深度学习模型、性能测量及稳定性证据。

|目录|主 case|通过|未通过|范围|
|---|---:|---:|---:|---|
|[mo-ds-lab](suites/mo-ds-lab/README.md)|100,000|97,000|3,000|pandas / NumPy / Spark / Flink，数学、类型、聚合、事务|
|[mo-complex-lab](suites/mo-complex-lab/README.md)|100,000|98,992|1,008|复杂 SQL、多表、窗口、子查询、数值与 ML 管线|
|[mo-long-lab](suites/mo-long-lab/README.md)|10,000|10,000|0|长分析链、最多 69 个 CTE、分阶段事务分析|
|[mo-demand-lab](suites/mo-demand-lab/README.md)|10,000|10,000|0|40 类业务分析需求、统计与约束优化决策|
|[mo-crosslab](suites/mo-crosslab/README.md)|10,000|10,000|0|跨 30 张表的 join、子查询、pandas / NumPy / Spark 组合|
|[mo-ml-lab](suites/mo-ml-lab/README.md)|20,000|20,000|0|PyTorch 残差 MLP、CNN、GRU、注意力、GCN 与模型存储|
|[mo-timeseries-lab](suites/mo-timeseries-lab/README.md)|10,000|9,800|200|18 源表时序需求、最多 147 窗口/88 CTE，Spark 与边界补测|
|[mo-analysis-needs-lab](suites/mo-analysis-needs-lab/README.md)|100,000|100,000|0|十类分析需求，100 个流程，pandas/NumPy/科学库及 Spark/Flink 补测|
|合计|360,000|355,792|4,208|不含补测、性能、试跑及中止尝试|

case 是有独立 ID 的参数化断言或完整工作流，不代表 360,000 种算法。各批次执行粒度不同，Spark/Flink 的共享 pipeline 错误可能影响多条断言；不能把未通过条数当作独立缺陷数。各目录 README 和 report.json 保留具体定义与限制。

## 完整材料在哪里

* `suites/`：可直接浏览的冻结代码、场景目录、输入 fixture、SQL 示例、依赖、报告与问题分析。
* `catalog/*.jsonl.gz`：360,000 条主 case 索引，包含批次、ID、状态、客户端、场景和原始 ZIP 成员/行号；ID 在每批内部连续且唯一。
* `catalog/summary.json`：直接遍历原始 case 记录得到的完整计数，未用补测覆盖早期失败。
* `archives/`：八个原始完整 ZIP 的 **40 MiB 分卷**。完整逐 case 记录、全部 20,000 个深度模型权重、其他模型、补测、性能、失败尝试和日志都在分卷中，且分卷全部是普通 Git 文件。
* `archives/manifest.json`：分卷 SHA256、原始 ZIP SHA256、字节数、ZIP 路径及主 case 数据文件列表。
* `catalog/source-files.json`：可浏览文件与其原始 ZIP 成员的字节 SHA256 对照。

分卷是为了满足 GitHub 单文件 100 MiB 限制；不依赖 Git LFS、外部网盘或 Release。还原后得到未经改写的原始测试目录。运行中的 MatrixOne 数据目录、服务二进制、Python 虚拟环境和缓存不属于 case 包，未提交。

## 获取和核验

```bash
git clone https://github.com/dengn/mo-test.git
cd mo-test
python3 tools/verify.py
python3 tools/restore.py                 # 还原全部到 work/，已有目标目录时拒绝覆盖
# 也可仅还原一个批次：
python3 tools/restore.py --suite mo-ml-lab --output /tmp/mo-test-replay
```

还原脚本仅依赖 Python 标准库，检查每个分卷和完整 ZIP 的 SHA256，以及所有 ZIP 成员 CRC。建议预留至少 7 GiB 磁盘空间。`--verify-only` 只校验分卷/ZIP，不解压。

```bash
python3 tools/restore.py --verify-only
gzip -dc catalog/mo-crosslab.jsonl.gz | head
```

## 重跑

各批次的完整运行步骤见其 README；请在还原后的目录中执行，而不是在仅供浏览的 `suites/` 中执行。使用独立的合成数据测试实例，配置 `MO_HOST`、`MO_PORT`、`MO_USER`、`MO_PASSWORD` 及对应批次的数据库变量。依赖按各批次 `requirements.txt` 安装；深度学习使用 CPU PyTorch，涉及 Arrow 的 Spark 深度流程使用 Java 17，Spark JDBC 写入显式使用 `READ_COMMITTED`。跨目录依赖和 JDBC JAR 可设置 `MO_JAR_DIR`；JAR 已保存在原始包中。

冻结代码保留执行时的路径和监控参数：`/workspace/mo-*-lab`、原服务 `server.pid` / `server.log` 路径，以及 ML 主程序的 PID 1384。换机器重跑时，在新运行副本中调整这些监控路径/PID；不要把历史 PID 当作当前服务。模型离线重放不依赖当前 MO 服务监控路径。

```bash
cd work/mo-ml-lab
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python replay.py 14999 --offline
python serving.py 14999 --offline
```

所有数据都是合成数据。测试会创建/写入/清理专用工作表，部分初始化脚本会重置测试表；仅在专用测试库运行。原始包中的本地默认测试账号不用于生产连接。

## 结果版本与已知问题

实际测试二进制提交为 `23d8f61252f3017dff218b530817a240206fd762`；工作区源码 HEAD `dd38098853ea197699ed3fac3e69dc53975ac061` 是另一版本。

已关联问题：[Spark 隔离级别 #29838](https://github.com/matrixorigin/matrixone/issues/29838)、[TANH #29839](https://github.com/matrixorigin/matrixone/issues/29839)、[statement_info TEXT 容量 #29809](https://github.com/matrixorigin/matrixone/issues/29809)、[ETL 上传 #29797](https://github.com/matrixorigin/matrixone/issues/29797)。其他早期复杂批次的差异、去重检索和失败 SQL 保存在对应报告与失败分析中。

通过意味着在记录的数据、容差和验收条件下兼容；不表示机器学习质量、生产规模、分布式容错或长期稳定性已获保证。性能基于同机 4 CPU / 16 GiB，许多指标包含客户端计算与往返，不能解释为 MO 纯 SQL QPS。后台日志事件与业务 case 失败分开计数，ML serving 对同一批模型的重放不新增 20,000 个训练 case。


## 追加的边界与混沌测试

另追加 **600,000 条主用例**（本轮 500,000 条已完成，后续两批各 50,000 条的完成状态见 manifest.json），覆盖极端 SQL、向量/全文、恢复、ETL、TLS/UDF/task/Iceberg、用户、多租户、发布订阅与 Git4Data。原有数据科学与 ML 测试及本次新增时序测试共 360,000 条保留；二者计数和报告分开。

[新批次目录与重放说明](BOUNDARY-CHAOS-600000.md) · [新批次完整性清单](manifest.json) · [500,000 条完成报告](suites/mo-stability-500000/REPORT.md)

~~~bash
python3 tools/materialize.py --verify-only --output /tmp/mo-boundary-verify
python3 tools/materialize.py --output /tmp/mo-boundary-replay
~~~

原有 tools/verify.py、tools/restore.py 和 archives/、catalog/ 不受影响。


## 窗口函数完整对比研究

[ClickHouse / DolphinDB / MO 窗口能力报告](research/window-gap/README.md) · [逐函数映射 CSV](research/window-gap/comparison.csv) · [固定版本及执行证据](research/window-gap/report.json)

ClickHouse 官方 14 个窗口入口中 MO 有 11 个、缺 3 个；DolphinDB SQL OVER 的 39 个中有 22 个原生映射、缺 17 个专用入口。17 个常见数学配置均已在 MO 用 SQL 组合实现并经独立 NumPy/SciPy 核验。更广的专用移动/时间/累计/TopN/技术指标 API 清单、算法/状态变体、NULL/frame/并列/增量执行差异另列，不把接口数量当作业务不可计算数量。ClickHouse 固定 26.9.16.11 实测；DolphinDB 为官方文档研究，没有运行时/跨库性能结论。234 条能力探针与研究不新增主 case 总数。

跨分区 LAG/LEAD 无类型 NULL 默认参数恢复型 panic 已提交 [#29925](https://github.com/matrixorigin/matrixone/issues/29925)；typed NULL 执行成功但错误返回 0，先前“正确通过”的结论已[更正](research/window-gap/CORRECTIONS.md)。所有研究文件的 SHA256 在 research/window-gap/artifact-manifest.json。此研究及八批的 archives/catalog 校验与另一个边界/混沌测试 manifest.json 分开，保留远端已有材料。


## 已提交的窗口功能需求

已用英文提交 19 个独立功能请求及 [#29950 汇总追踪](https://github.com/matrixorigin/matrixone/issues/29950)，附用途、完整合成 SQL、三次拒绝/正确结果对照与回归范围。已有 #10182 已补充回归验证。完整列表和全部 297 次补充验证见 [窗口 feature issue 索引](research/window-gap/feature-issues/README.md)；不新增主 case 总数，不更改既有分卷和原始结果。


## 十类分析需求新增 100,000 个 case

[完整分析需求测试](suites/mo-analysis-needs-lab/README.md)涵盖严格时点特征、增量修正、流式事件、实验因果、归因旅程、层级预测、时序图、风险模拟、空间轨迹与模型监控。每类 10,000 个，共 100,000 个唯一逻辑 case，90,632 条不同 SQL。每例都在 MO 执行并校验完整返回值，随后用 NumPy/pandas/SciPy/sklearn/NetworkX/Shapely 计算并与独立数学参考比较；科学算法运行在客户端。

初次 99,392 个完整流程通过；608 个 SQL 值校验通过后遇到 Python `np.isnan(None)` 的脚本问题。仅修正空值检测后，这 608 个全部重新执行并通过；最终逻辑 case 为 100,000/100,000。原始代码、失败、复测及每条目录索引的原 ZIP 成员/行号均保留，重复尝试不增加主 case ID。

Spark Structured Streaming 与 Flink bounded JDBC 各有 10,000 组补测通过，使用共享真实 pipeline，单列不计入主 case。另有 1,000 个冷启动、50 个未来信息泄漏及 100 个速度异常正/负控制；主来源 19 表 87,672 行在执行前后逐值/哈希审计一致。观测期间服务进程未更换，OOM 计数未增加，控制台采样区间无 panic/fatal。

[报告](suites/mo-analysis-needs-lab/report.json)包含完整方法、范围、修正及内存压力记录；200 次隔离、预热客户端读测覆盖 50 条代表查询，各场景中位数约 3.0–10.0 ms，包含取数和 DataFrame 构造，不是生产吞吐率。完整逐 case SQL、参数、预期/实际输出、检查点状态、日志及可重放代码都在新分卷中。


## 五个开源 GIS 应用与 TTL 能力核验

[GeoServer、pygeoapi、QGIS、uMap、Maputnik 的真实端到端测试](suites/mo-gis-app-projects/README.md)：51 个项目/后端/接入阶段工作流，保留原生失败与适配后结果；新增确认的几何协议缺陷 [#30046](https://github.com/matrixorigin/matrixone/issues/30046)。

[TTL 源码、文档与 SQL 实测](suites/mo-ttl-check/README.md)：当前 main 无原生行/表 TTL，定时 SQL task 删除过期行已验证。两套后续核验均不计入原有 600,000 条主 case。

## 开源应用原生回归

新增可独立执行的 [应用回归套件](suites/mo-app-regression/README.md)：Gotify、Blocky、Plik、Ergo、Documize、Huginn、ntfy、Memos、Baikal、FreshRSS、Adminer、phpMyAdmin、Kanboard、YOURLS、Grafana、Matomo、Gogs、Apache Answer、OpenCart、Wakapi、Superset、Strapi、WordPress、Wagtail 的原生业务/权限/精确值/重启测试，以及 20 个完整 SQL fixture（含 4 个显式开启的 panic）。统一入口输出 JSON/JUnit，提供可复用 [GitHub Actions](.github/workflows/app-regression.yml)。

[1000 项候选名单](suites/mo-app-regression/catalog/projects-1000.csv) 与 [历史运行/迁移状态](suites/mo-app-regression/inventory.json) 分开保留：61 个真实尝试、58 个基本业务通过、24 个独立驱动。其余项目继续迁移；不计入已有历史批次的 case 总数。


## #29927 当前 main 回归核验

[原始并发索引竞态复测](suites/mo-issue-29927-recheck/README.md)：旧版本 3 轮中 1 轮复现且重启后仍坏；main `3e50e1b3` 五轮通过，负载结束及重启后共 454 项检查通过，1,081 条确认写入无缺失/错值。复测支持原报持续性损坏已修复，尚未确定具体修复 PR。原有主 case 计数不变。



## BI 与分析 case 自动回归

新增独立的 [BI/复杂分析回归套件](suites/mo-bi-regression/README.md)，纳入 20,000 个分析 case、6,820 个 Metabase 查询构建器 case、其他 BI 共用的 534 个 SQL、800 个 Rill 原生指标、268 个复杂/巨型 SQL 及 spill 回归。确定性输入与独立预期可在新环境重建，真实 BI API/SDK 与 SQL 重放分别登记；输出 JSON/JUnit，严格门禁与保留失败标签的观察模式分开。

[可调用 CI](.github/workflows/bi-regression.yml) · [执行范围与验证](suites/mo-bi-regression/VALIDATION.md)。此套件与原历史批次计数分开，不改 archives、catalog 或旧 manifest，不将跨工具重复执行当成新增唯一 SQL。

## AI 框架 MatrixOne 自动回归

[AI 框架回归套件](suites/mo-ai-frameworks/README.md)纳入 26 个已适配项目、14 个隔离依赖组、43 个必跑测试；JSON/JUnit 对失败、跳过、缺失与超时严格判失败，带随机测试库和运行归属检查清理。包括 LangChain/LangGraph、LlamaIndex、Haystack、Mem0、LightRAG、OpenAI Agents、ADK、CrewAI、AgentScope、CAMEL 等真实接入角色，模型使用确定性替身。

[Top100 策展目录](suites/mo-ai-frameworks/catalog/top100.csv)保留 100 项源码初筛、29 项实际接口/原生对照证据，正向门禁不计入 MLflow/Langfuse/pgvector 的原生阻断或对照项。26 项、43 个用例本地全部通过；沿用现有自托管 runner 的 [GitHub Actions](.github/workflows/ai-framework-regression.yml)尚待远端实际执行。此套件独立计数，不修改已有大批次 case 总数。

## 本会话数据生态与 ETL 用例

[完整目录、状态与重跑说明](suites/mo-ecosystem-session/README.md) · [执行索引计数](suites/mo-ecosystem-session/catalog/summary.json) · [32 工具重载状态](suites/mo-ecosystem-session/heavy-status.json)

新增汇集 13 个材料目录，含 ETL/CDC/编排/客户端/压力/EOS 正反例及关联 issue。两轮各 10,000 条主用例已有完整执行记录；最新 32 × 5,000 重载计划中实际执行 27,559 条，剩余 132,441 条未执行。这里保留 **47,559 条主执行记录**，包含 MySQL 对照；预检、原生失败、补测和故障反例另存，不与原有批次混加。Airbyte 原生 MO sink 阻断及 Fivetran 官方 SDK 本地范围明确列出。

```bash
python3 tools/ecosystem_materialize.py --verify-only
python3 tools/ecosystem_materialize.py --output work/ecosystem-session
```

13 个归档及逐成员/逐文件 SHA256 清单、冻结源码和可配置的核心/读取重跑入口在独立目录内。校验工具核对索引与原始记录及计划唯一性，恢复拒绝覆盖既有目录，不执行服务生命周期脚本。该组实际 MO 提交为 `652c643666428f1c434e03369834f2a9bead7c27`，与前述数据科学批次版本不同；不代表当前 main、完整长稳或跨系统 exactly-once 已认证。

