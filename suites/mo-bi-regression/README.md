# BI 与复杂分析自动回归

将本会话构建的分析数据、SQL、指标定义及真实 BI 测试移入可独立执行的 mo-test 套件。无需还原历史分卷，无需原工作目录；使用新建的随机测试库，输出逐 case JSON 和 JUnit，失败返回非零。

## 导入范围

| 语料 | 唯一 ID | 覆盖 |
| --- | ---: | --- |
| `analytics.jsonl.gz` | 20,000 | 100 个 SQL 模板 × 200 个确定性场景，10 个业务域、20 种分布与边界 |
| `metabase.jsonl.gz` | 6,820 | 原生 MBQL 查询构建器：指标、嵌套问题、漏斗、留存、库存及跨事实模型 |
| `sql-projection.jsonl.gz` | 534 | 30 个原始业务查询及 Metabase 实际生成的共享分析 SQL，用于其他 BI 原生路径 |
| `rill-metrics.jsonl.gz` | 800 | 10 个原生指标视图、维度分解、去重与加权比率 |
| `extreme.jsonl.gz` | 268 | 150 个复杂业务分析及 118 个结构/长度递增场景；包含最大约 8.4 MB 的 SQL |
| `models.json` | 24 | 事实粒度、实体聚合、严格有序漏斗、首次活跃 cohort、结存递推及跨事实模型 |
| `spill.json` | 14 | 百万行排序、聚合、窗口、各种 join 及 NULL-aware 负控制的完整输出哈希 |

这些语料有重叠，原生工具的重复执行也不是新增唯一 SQL。**不将这些数量相加到仓库原有的历史主 case 总数。** 独立预期来自原 CSV/DuckDB/Python 核验，不从当前 MatrixOne 的返回值生成预期。

核心生成器重建 14 表、356,840 行，逐表 CSV 字节哈希必须与原始版本一致。另生成 100,000 订单的原始业务 fixture，以及组织、图、日历和目标小表。装载后按声明的 Decimal 位数及完整字段逐值审计；复用 fixture 时也重新核对完整字段，不能仅靠行数通过。

金额列精确比较，不用浮点容差掩盖金额损失。只有 case 登记的统计列和比率沿用原有显式容差；整数 AVG 仅相应首列允许规定的四位小数舍入差。NULL、空字符串、重复行、完整行数和登记的排序均参与比较。

## 安装与 SQL 回归

Python 3.12 / Linux x86_64；先准备专用 MatrixOne 测试实例。

```bash
cd suites/mo-bi-regression
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python verify.py
.venv/bin/python -m unittest discover -s tests -v

# 通过环境配置 MO_HOST、MO_PORT、MO_USER、MO_PASSWORD；密码没有默认值。
# 远程 TLS 连接可配置 MO_SSL_CA，并保持主机名/CA 验证。
.venv/bin/python run.py --profile smoke --out artifacts/smoke-001
.venv/bin/python run.py --profile sql --out artifacts/sql-strict-001
.venv/bin/python run.py --profile sql --mode observe --out artifacts/sql-observe-001
.venv/bin/python run.py --profile bi --list --out artifacts/not-created
```

`smoke` 包含 198 个微小金额/密集分布的受支持模板 case 和全部 534 个共享 SQL，严格门禁共 732 项。`sql` 执行全部 20,534 项，包含相关范围聚合限制的 200 个变体。原测试二进制 `23d8f61252f3017dff218b530817a240206fd762` 上这 200 项精确匹配 [#28298](https://github.com/matrixorigin/matrixone/issues/28298) 的错误代码和签名；错误后还核对原连接 `SELECT 1`。修复后必须与原独立答案一致才能通过。

所有 profile 支持 `--expected-commit <完整40位SHA>`；版本不符时，在创建测试库前失败。默认自动清理**本次实际创建**的库；`--keep-data` 可保留诊断数据。输出目录已存在则拒绝覆盖。`--fixture-state artifacts/<run>/fixture-state.json` 可复用同一实例上的完整审计数据；复用的库不会自动删除。不同运行的 BI 元数据与私有 runtime 使用新标识，不能依赖历史卡片或数据源 ID。

## 真实 BI 入口

复制并修改 [native-config.example.json](native-config.example.json)，配置专用的已初始化服务或官方 SDK。账号字段支持 `username_env`、`password_env`、`token_env`，只解析实际选中的工具。缺配置、SDK、版本或完整输出会失败，**不会静默跳过或退回 SQL 冒充原生 BI 测试**。

```bash
.venv/bin/python run.py --profile metabase \
  --native-config /private/bi-runtime.json --out artifacts/metabase-001
.venv/bin/python run.py --profile bi --tool redash --tool rill --mode observe \
  --native-config /private/bi-runtime.json --out artifacts/native-001
.venv/bin/python run.py --profile bi --mode strict \
  --native-config /private/bi-runtime.json --out artifacts/all-native-001
```

| 工具固定版本 | 实际接入路径 | 回归边界 |
| --- | --- | --- |
| Metabase v0.64.1.5 / MariaDB JDBC 2.7.15 | 新建数据源、24 个 native SQL 模型、6,820 个 MBQL、10 个保存指标及 50 次仪表板筛选，共 6,880 项 | 显式模型避开已有 grants/字段自动同步问题；不是同步修复 |
| Superset 6.1.0 / PyMySQL 1.2.3 | 534 个 SQL Lab、10 个视图注册、物理表保存指标及 8 次 chart-data，共 553 项 | DECIMAL type 0/tuple 互操作问题；视图反射在 HTTP 中可能仅返回不透明 `Fatal error`，该响应仍是未知失败 |
| Grafana 13.2.3 / MySQL plugin 13.1.2 | 数据源健康及 534 个原生查询，共 535 项 | 保留 `details.verboseMessage` 的具体错误；unsupported collation 关联 [#29206](https://github.com/matrixorigin/matrixone/issues/29206) |
| Redash 26.9.0 / mysqlclient 2.1.1 | 官方 MySQL runner 与**生产 JSON encoder**，534 项 | 不用自制编码器保留 Decimal 来掩盖生产 float 损失；未覆盖完整 Web 调度器 |
| DataEase 2.10.17 / Connector/J 8.2.0 | 保存 MySQL 数据源、实际 SQL-preview API，共 535 项 | 等待数据源异步就绪；100 行预览截断保留失败标签；未覆盖完整图表与跨数据源 |
| Evidence mysql plugin 1.1.6 | 官方插件 `rows()`，534 项 | 没有诊断用 collation monkey patch；不声称 native 页面构建通过 |
| Rill 0.90.5 | 本次创建的私有项目、原生 MySQL 导入与 800 个 metrics-view 请求 | 指标在 Rill 本地 DuckDB 执行；不作为 MO 聚合下推证据；保留 DOUBLE 精度损失 |
| Zeppelin 0.12.0 / Connector/J 8.4.0 | 保存笔记本与 534 个 `%jdbc` 段落 | 制表符/换行的 TABLE 格式问题单列；不是数据库值错误 |
| SQLPad 7.5.7 | 534 个原生 REST batch、完整结果及保存查询，共 535 项 | 已归档的旧工具；检查异步完成、`incomplete` 和结果上限 |
| Lightdash 2.573.1 | 官方 warehouse factory 和 SQL builder 的四项探针 | 无原生 MySQL/MatrixOne adapter；**未执行 MatrixOne SQL**，拒绝保留 known failure |

Superset、Grafana、SQLPad、DataEase、Zeppelin 使用专用 HTTP 服务，Metabase 必须完成应用账号初始化。DataEase 使用官方 desktop 模式；需要可写的外部缓存/日志和独立 H2 元数据库，不能把 `/opt` 或 H2 schema 配置错误算成 MO 缺陷。Zeppelin 需预装 JDBC 驱动并允许更新专用解释器，服务端输出上限至少 10 MiB，解释器最大行数设为 100,000。这些服务都是回归专用的，不能指向已有生产 BI 工作空间。

Redash SDK 使用官方源码/镜像中的 Python，应用需要正常设置 cookie/secret 环境；其 `redash.__version__` 与 mysqlclient 版本实际核对。Evidence/Lightdash 的 `module_root` 指向已安装的对应官方 npm 包。`command` 是 argv 数组，不经过 shell；支持 `{driver}`、`{input}`、`{output}`，容器可用 `path_map` 映射挂载路径。容器中的数据库地址用 `database_host` 指定；`localhost` 指向容器自身。Rill 校验指定二进制的 SHA256 和真实 `version` 输出，并等待全部十个指标视图就绪。

参考固定镜像见 [runtime-pins.json](runtime-pins.json)。Superset HTTP 服务没有统一的版本端点，因此配置中的 image digest 是由部署方核验的启动身份；DataEase 验证实际提供的 JAR 哈希及 manifest 版本，其他可用 API/SDK 自行读取版本。更换工具版本须更新 pin 并重新验证，不能盲用本次基线。

当前已知客户端精度/格式差异仅在**完整匹配历史失败值指纹**且**当前 MO 源 SQL 仍与独立答案一致**时归类为 known failure。独立答案不变，严格模式仍失败；新增偏差、少行、错误值或不透明的异常不能靠观察模式掩盖。

## 严格门禁与观察模式

`strict` 是默认门禁：金额/数值不符、缺运行时、未知错误、截断以及 known failure 全部非零退出。`observe` 仅允许已识别的 known failure 保留为 JUnit `skipped`；报告的 `passed` 仍为 false，不可替代发布门禁。没有记录也失败。自然错误、取消、watchdog、预览截断和已知限制不会被汇总成通过。

`--limit N` 是显式缩小选择，写入报告；不代表完整覆盖。Metabase 的模型与 60 项保存对象检查仍执行，Lightdash 的四个 adapter 探针不提交 SQL。所有结果通过 case ID 回查压缩语料的 SQL、MBQL、独立预期和容差。

## 长 SQL 与 spill

```bash
.venv/bin/python run.py --profile extreme --dedicated-instance --mo-pid <actual-pid> \
  --out artifacts/extreme-001
# 额外包含历史错误、未尝试、时间/内存边界；资源触发仍失败，不叫 MO 自然崩溃。
.venv/bin/python run.py --profile extreme --include-boundaries \
  --dedicated-instance --mo-pid <actual-pid> --out artifacts/boundaries-001
.venv/bin/python run.py --profile spill --dedicated-instance --mo-pid <actual-pid> \
  --spill-root /path/to/owned/mo-data/local2/__spill \
  --metrics-url http://127.0.0.1:7001/metrics --out artifacts/spill-001
```

`extreme` 默认重放历史有界通过的 257 项；全部 268 项仍在语料中，11 个边界未默认选择明确登记。逐查询超时、4 GiB RSS 及 PID starttime 监测会取消本次查询，不自动重启或杀死外部 MO 服务。必须使用有独立资源上限的专用实例；进程 PID、目录及 metrics URL 必须属于同一实例。

`spill` 创建新的 1,048,576 行宽表及 join 键，设置明确的 session spill 阈值和优化器估计 fixture hook；该 hook 不改源行。完整输出流式哈希、EXPLAIN ANALYZE、spill counter 增量、目录文件及 `/proc/<pid>/fd` 中已 unlink 的实际文件共同记录。13 项要求真实 spill，`NOT IN` 的右侧含 NULL 是短路空结果的**无 spill 负控制**。只有 SQL 完成不能通过正向 spill 门禁，还要求清理边界干净且原连接可用。

14 项 operator profile 与资源/取消回归分开。`spill_recovery.py` 复制提供的本地角色配置，在新私有目录启动**本轮自己创建的子进程**，执行真实 spill 后取消、1 MiB 低磁盘拒绝、128/512 MiB 宽排序 A/B、原连接可用和临时文件清理六项检查：

```bash
.venv/bin/python spill_recovery.py --dedicated-instance \
  --binary /path/to/mo-service --binary-sha256 <verified-binary-sha256> \
  --config-dir /path/to/unused-port-local-config \
  --expected-commit <actual-build-full-sha> --out artifacts/spill-recovery-001
```

原端口已占用、配置指向外部数据目录/远端文件服务/集群、二进制 hash 不符或空闲磁盘少于 2 GiB 时拒绝，不接管已有实例。只停止/重启自己的 Popen 子进程，原配置不改写；私有角色配置和 server 日志不上传。128 MiB/低磁盘下的受控资源拒绝是明确的资源保护断言；未来优化若能正确完成同一查询也记录为有效的边界接受，不能把性能改善判成错误值。512 MiB 阶段要求完整宽排序结果与独立哈希一致。完整执行证据及本轮边界见 [VALIDATION.md](VALIDATION.md)。

## CI

[bi-regression.yml](../../.github/workflows/bi-regression.yml) 可手动执行或由其他工作流调用：

```yaml
jobs:
  analytics:
    uses: dengn/mo-test/.github/workflows/bi-regression.yml@<reviewed-commit>
    with:
      profile: smoke
      mode: strict
      expected_commit: <actual-build-full-sha>
    secrets: inherit
```

配置 `MO_TEST_HOST/PORT/USER/PASSWORD` 密钥；native profile 另设置 runner 上私有 JSON 路径 `MO_BI_NATIVE_CONFIG`。压力 profile 显式确认 `dedicated_instance`，并提供 `MO_BI_SERVICE_PID`；spill 还需 `MO_BI_SPILL_ROOT`、`MO_BI_METRICS_URL`。托管 `spill-recovery` 另需 `MO_BI_RECOVERY_BINARY`、`MO_BI_RECOVERY_BINARY_SHA256`、`MO_BI_RECOVERY_CONFIG_DIR` 及可选 `MO_BI_RECOVERY_SQL_PORT`；初始化凭据须与 MO 环境一致。runner 是 `[self-hosted, Linux, X64]`。工作流序列化对同一专用实例的运行，输出仅上传 `artifacts/`，不上传 `runtime/` 的账号、SDK 输入、项目连接配置或原始应用日志。

本 PR 提供可调用入口，不改已有应用工作流，也不自动启用远端定时作业；调度方可将上述调用接入现有 nightly。详尽 JSON/JUnit、语料 SHA 和当前目标版本可供历史对比。初始导入的旧失败、已验证修复和未来再次失败需保留为不同运行，不覆盖原始证据。
