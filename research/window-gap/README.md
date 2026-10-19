# ClickHouse / DolphinDB 与 MatrixOne 窗口计算能力对照

以实际运行的 MO commit `23d8f61252f3017dff218b530817a240206fd762` 为基准。ClickHouse 使用固定官方二进制 **26.9.16.11**，运行只读本地 SQL；DolphinDB 依据抓取时的官方文档和 3.00.5 教程，不声称已实测 DolphinDB 服务。接口存在、参数兼容、数学可组合与专用增量执行内核分别统计。

|口径|对方范围|MO 原生对应|缺少专用对应|
|---|---:|---:|---:|
|ClickHouse 文档列出的窗口入口|14|11|**3**|
|DolphinDB SQL `OVER` 函数|39|22|**17**|
|ClickHouse 公开聚合内核注册清单|191|16 个明确原生候选执行通过|175 个没有一对一专用映射|
|DolphinDB 专用移动/时间/累计/TopN/技术指标 API|152|0 个同名 API|152 个接口需要适配|
|DolphinDB 上述 API 仅归并 m/tm/cum 前缀后的算子族|78|13 个基础内核族|65 个无一对一专用内核族|

第三行来自固定 ClickHouse 二进制的聚合注册清单；按官方“聚合可用于窗口”规则作为候选，未对 191 个内核的全部签名逐一执行窗口验证。它计的是实现/算法/状态变体，包含分位数不同算法、加权与多分位形式及其他领域聚合；不能解释为 175 项业务不可计算。16 个原生候选是“能够执行”，不是“所有行为完全兼容”：其中 groupBitAnd, groupBitOr, groupBitXor 的全 NULL 框架身份值/NULL 输出与符号约定存在差异，完整值均保留。最后两行也不等价于 152/65 种无法在 MO 计算的数学公式。13 个基础族的接口边界、NULL 和最小样本数仍需适配。

ClickHouse 的三个额外窗口入口为 **lagInFrame、leadInFrame、nonNegativeDerivative**。MO 已实现标准的 ROW_NUMBER/RANK/DENSE_RANK/PERCENT_RANK/CUME_DIST/NTILE/FIRST_VALUE/LAST_VALUE/NTH_VALUE/LAG/LEAD；这不保证每种参数组合没有缺陷。依据：[官方窗口入口列表](https://clickhouse.com/docs/reference/functions/window-functions)，[固定版本](https://github.com/ClickHouse/ClickHouse/releases/tag/v26.9.16.11-stable)。

DolphinDB 缺少直接原生映射的 17 个 SQL 入口：**sum2, imin, iminLast, imax, imaxLast, skew, kurtosis, firstNot, lastNot, prod, wavg, wsum, corr, covar, beta, atImax, atImin**。其余 22 个按标准窗口、方差/标准差别名、中位数和线性分位数进行显式映射。`percentile` 的额外插值模式不等同于 MO 的默认线性 ordered-set 分位数。依据：[DolphinDB SQL 分析函数完整表](https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html)。

对这 17 项，我们已在 MO 中组合实现一个明确的常见数学配置，并对全部输出使用原始十行 fixture 的 NumPy/SciPy 独立核验通过，包括相对窗口位置、最早并列、NULL 跳过、有偏偏度、Pearson 峰度和样本协方差。代码为 `rewrites.py`，SQL/完整预期与实际结果在 `results/rewrites-all17.*`。这证明该配置可算；不证明 DolphinDB 的所有参数、矩阵/数组、特殊值、增量复杂度与性能等价。

NULL 默认值也需迁移适配：ClickHouse 的 FIRST_VALUE/LAST_VALUE 默认跳过 NULL，MO 在本 fixture 保留 NULL；表中专用映射使用显式尊重 NULL 的 ClickHouse 变体进行比较。

实测共同窗口之外的缺口包括 **GROUPS 框架、IGNORE NULLS（FIRST/LAST/NTH/LAG/LEAD）、窗口内 DISTINCT、FILTER 聚合子句**。当前 ClickHouse 版本同样拒绝 EXCLUDE；因此新时序场景中的 EXCLUDE 失败不能算作 MO 相对 ClickHouse 独有的差距。MO 的命名窗口及继承通过；DateTime RANGE 的 INTERVAL 偏移在 MO 通过而此 ClickHouse 版本拒绝，不能漏记 MO 已有能力。

**执行缺陷：**三行、两分区的 `LAG(value,1,NULL)` / `LEAD(value,1,NULL)` 会在 MO 返回 20101，包含 `index out of range [2] with length 1` 的恢复型 panic。`CAST(NULL AS DOUBLE)` 仅执行成功，最后一行错误返回 0，不能作为正确 workaround；省略默认参数在此 fixture 返回正确 NULL。ClickHouse 对应三行查询正常。`results/null-default-repro.json` 保存原始证据，复测与更正见 [CORRECTIONS.md](CORRECTIONS.md)；已提交 [#29925](https://github.com/matrixorigin/matrixone/issues/29925)。此缺陷不从“11 个已实现入口”扣掉，但必须进入兼容性结论。

**时序专用能力：**MO 已实测支持原生 INTERVAL、SLIDING 和 PREV/NEXT/LINEAR/VALUE 填充，不能写成“MO 没有时间窗口”。本二进制使用 `_wstart` / `_wend` 伪列；文档中部分 `_wstart(ts)` 形式被拒绝。依据：[MO 时间窗口](https://docs.matrixorigin.cn/mo/zh/latest/MatrixOne/Develop/read-data/window-function/time-window.html)，执行记录 `results/native-mo-time-windows.json`。

迁移 DolphinDB 必须逐项处理：m/tm/cum 的边界和输出维度；`minPeriods` 默认值；tm 系列的左开右闭窗口；同时间戳记录的当前可见范围；mrank 的局部窗口排名与 SQL RANK 的整个分区排名；TopN 的 oldest/latest/all 并列策略；样本/总体方差；Pearson/超额峰度；EWM 的 adjust/ignoreNA/时间权重。普通 RANGE/SUM 的可算性不等价于专用增量算子的复杂度和有状态流执行能力。依据：[移动窗口](https://docs.dolphindb.com/en/Functions/Themes/mFunctions.html)、[时间窗口](https://docs.dolphindb.com/en/Functions/Themes/tmFunctions.html)、[累计窗口](https://docs.dolphindb.com/en/Functions/Themes/cumFunctions.html)、[TopN](https://docs.dolphindb.com/en/Functions/Themes/mTopN.html)、[EWM](https://docs.dolphindb.com/en/Functions/e/ewmMean.html)。

优先级建议：先修三行可复现的 NULL 默认参数执行错误；然后补 GROUPS / IGNORE NULLS / DISTINCT 窗口及 FILTER 语义；再按需求补滚动相关/协方差/回归、加权统计、局部 rank/分位数/TopN、EWM 和极值位置。更后面是有状态增量执行、事件时间水位、跨窗口更新和流引擎接口。业务 ROI 应在同数据、同参数、同正确性规则的隔离性能测量后判断，本次没有跨库性能结论。

完整可检查材料：`report.json`、`comparison.csv`、`dolphindb-catalog.json`、`operator-families.json`、固定 ClickHouse 注册表及 `results/clickhouse-kernel-matrix.json`、234 条主要能力探针、17 项组合数学复核和原生时间窗口记录。来源元数据记录 URL/抓取时间/可下载页的 SHA256；ClickHouse 网站原始抓取返回 403，但通过官方网页浏览与固定二进制注册表/实测完成交叉验证。原始网页只在本地缓存，不上传全文。内部调试和占位内核、通用行向量函数、插件和流引擎不混入上述函数数。

## 复现与材料边界

安装 `requirements.txt`；在自己的专用合成测试库设置 `MO_HOST/MO_PORT/MO_USER/MO_PASSWORD/MO_TS_DATABASE`。本地默认 root/111 仅是原测试实例账号。只读能力探针使用内联 fixture；`time_windows.py` 会创建/写入/清理私有 `ts_gap_time_window` 表。

ClickHouse 使用官方固定版本 `v26.9.16.11-stable` 的 linux-amd64 `clickhouse-common-static-26.9.16.11-amd64.tgz`；归档和二进制的 SHA256 见 `clickhouse-version.json`。将 `CLICKHOUSE_BINARY` 指向该 `clickhouse` 可执行文件（或放到 `cache/clickhouse`），按 SHA256 核验后重跑。二进制和网页全文不上传；官方来源 URL/抓取元数据、抽取的 API 清单、裸函数注册表和本次 SQL/全量结果均已保留。`sources/mo-function-registry.json` 保存实际 MO 提交的注册名及源码哈希，重跑内核清单不依赖未发布的源码缓存。

```bash
python probes.py                  # 两引擎能力对照，不需要 DolphinDB 服务
python kernels.py                 # 固定 CH 注册表与 MO 专用映射
python rewrites.py                # 17 项独立数学复核
python time_windows.py
python null_default_repro.py
python report.py
```

这些脚本会改写自己的结果文件，建议先复制一个新的运行目录。`fetch_sources.py` 可重新抓取官方页面，但网站可随时间改变或拒绝抓取；当前结果应以保留的 URL/时间、清单、固定二进制版本和原始执行证据为准。234 条主能力探针不是新增的 234 个时序主 case，研究内容不混入仓库主 case 总数。DolphinDB 官方接口名全部被逐项研究；未连接 DolphinDB 的运行时行为及性能仍是明确的验证边界。


复测 NULL 的实际值与 NULL 位：设置当前 MO_SERVER_PID，并运行 `python null_default_value_recheck.py`；24 个查询分别断言 panic、typed NULL 错值及正确控制，结果另写 `results/null-default-value-recheck.json`。


## 已发布的英文功能请求

已发布 19 个独立功能请求与 [#29950 汇总追踪](https://github.com/matrixorigin/matrixone/issues/29950)，并给已有 #10182 补充回归案例。完整索引、297 次最终只读验证及重跑脚本见 [feature-issues/README.md](feature-issues/README.md)。这些补充验证不新增主 case 总数。
