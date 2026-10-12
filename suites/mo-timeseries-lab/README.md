# 10,000 个复杂时序窗口分析需求测试

**50 类分析需求 × 200 个配置 = 10,000 个实际执行、SQL 唯一的主 case；9,800 通过，200 因 GROUPS/EXCLUDE 高级框架不支持而失败。** 每个 case 是完整分析程序，不把每个窗口、输出行或阶段计为新 case。50 类需求及 SQL 见 `scenario-catalog.json` 和 `examples/`；最长程序包含 147 个窗口、88 个 CTE、25 个 JOIN，最大 SQL 29,342 字节。复杂度最大值可能来自不同 case。

需求包括修订/迟到数据快照、多币种收入、撤销、异常基线、波动与趋势、滞后预测、回撤/恢复、状态岛、缺失携带、会话/漏斗、不规则 ROWS/RANGE、库存/容量/预算、图邻居冲击、行业反馈、加权衰减、局部回归、多层非线性窗口反馈及物化事务。18 张合成表、175,292 行原始输入保存在 `inputs/*.csv.gz`，无生产数据。

## 结果与独立验收

* 主批次：10,000 完成，9,800 通过，200 `sql_or_stage_error`，无结果不一致或参考程序错误；200 个失败全部属于 family 41 同伴排除需求。完整 SQL、参数、expected/actual 全量数组、客户端、耗时、事务步骤都在 `cases.jsonl`，不是只有摘要或哈希。`case-index.json` 与 `report.html` 可搜索全部 ID。
* 参考：从原始 18 表建立 DuckDB 独立 SQL 对照，核对所有通过 case 的 4,559,615 行完整结果；连续值 rtol=atol=1e-7。最终对声明的离散/时间字段精确核对 23,229,043 个单元格，避免时间值相对容差掩盖差异。
* 原生算法：200 组 pandas 重建日级事实及不规则事件，分别全量核对 MO 与 DuckDB；264 个窗口配置覆盖 22 类需求，由原生 NumPy 另行核对部分列或深层最终 score。600 条 native 记录中的另外 336 条仅核对基础事实，不能写成 600 个独立完整窗口算法验证。
* 物化流程：200 个分析结果实际绑定写回，服务器二次窗口、跨连接可见性、100 次提交/100 次回滚及清理通过，写回 87,749 行。七张私有表最后为空。
* Spark：100 个额外原生 SQL 窗口/JDBC sink 流程全部通过；18 源表 JDBC 全内容审计、Spark 计算、实际 JDBC 写入及 MO 读回均核验。Java 17，Spark 3.5.3，local[2]，堆 1 GiB，READ_COMMITTED。Spark ID 与主批次重叠，另计，非 Python worker 计算。
* 边界探针：64 个，40 通过，24 因 GROUPS/EXCLUDE 不支持而失败。错误保持在原始结果中，不改写为其他 frame 后算通过。
* 独立性能：240 次额外查询全部正确。NumPy/PyMySQL 的 1/2/4/8 并发混合批次吞吐约 4.83/8.17/13.20/10.29 查询/秒；pandas/SQLAlchemy 约 4.80/8.40/8.30/8.49。每点只有 30 查询，主批次及 Spark/研究客户端已结束；参考验证在计时批次之后。数值含 query/fetch，批次吞吐还含连接和线程开销，是同机小规模观察，不能作客户端排名、纯 MO 内核 QPS 或跨数据库性能结论。

最初的 200-case 试跑及纯参考预检尝试保留在 `attempts/`，与最终结果分开。修正 MO 保留字别名以及整数 AVG/除法的显式 DOUBLE 转换后，最终 pilot 196 通过、4 个高级 frame 失败；容差未放宽。DuckDB 对深层 layer CTE 单独添加 AS MATERIALIZED，避免参考端反复内联；MO SQL 未改，原生 NumPy 另核对深层数学结果。

## 稳定性与适用边界

主批次 26.74 分钟，318 次健康探测、0 次错误；同一服务 PID 1384 最后仍存活，原始源表最终完整哈希不变，OOM/OOM kill 增量为 0。但 cgroup `max` 增量 19,868，表明有内存限额压力/回收，不能说没有内存压力。Spark 和性能客户端有独立 wall/RSS guard，未触发停止。

同服务的能力研究探针发现三行、两分区 `LAG/LEAD(value,1,NULL)` 返回 20101 恢复型 vector panic；typed NULL 对照正常。研究完整证据另在仓库 `research/window-gap/`，该事件不是主批次 200 个 frame 失败，也不是服务进程崩溃。

后台 statement_info/ETL 容量问题再次出现：当前测试库一条用户状态 Success 的记录，exec_plan 为合法 JSON、1,168,340 字节，超过 TEXT 65,535 字节，长度与上传错误一致。原记录保存在 `telemetry/`。不能用截断 statement 唯一归属到某个 case，不能把 135 个旧失败文件重试全算成本批新增，也不能推断永久丢失或已恢复。已关联 #29809/#29797。另审阅了两个 table-stats cnt=0 日志及一对 invalid-task/IndexUpdateTask heartbeat 日志，未建立背景任务恢复结论；详细计数按日志上下文而非业务请求计，见 `server-log-review.json`。

数据是固定 received-time 快照下的回顾分析，不保证在线训练特征 point-in-time 无泄漏；显式未来窗口仅用于描述分析。前置 20 天历史不足长 frame 时保留部分 frame 语义。时间使用 UTC 整数分钟；合成 offset 切换不是完整 IANA 时区验证。测试是单实例本地读写，不覆盖分布式容错和长期 soak。

## 版本与重跑

MO 实测二进制 commit `23d8f61252f3017dff218b530817a240206fd762`，SHA256 `49d2d31eeb6c8b3151612aa10314c1081cb47908410e7321fae389b0db0c80e7`；工作区源码 HEAD 是另一版本。环境 4 CPU/16 GiB，Python/依赖/Java/JDBC 哈希见 `environment.json`。

先用根仓库 `tools/restore.py --suite mo-timeseries-lab` 还原完整包，然后在**新的运行副本**中执行；冻结副本中已有 `meta.json` 的完成目录会拒绝覆盖。使用专用合成测试数据库；`--setup` 会创建/重置源测试表。根据新机器调整监控路径，设置当前服务 PID，不能沿用历史 PID。监控代码保留执行时路径 `/workspace/mo-ds-lab/server.pid` / `server.log`。

```bash
python3 -m venv /tmp/mo-ts-venv
/tmp/mo-ts-venv/bin/pip install -r requirements.txt
# 在新运行副本中：保留 inputs 和程序；将 results 移入独立历史目录。
export MO_HOST=127.0.0.1 MO_PORT=6001 MO_USER=root
export MO_TS_DATABASE=ds_timeseries_replay
export MO_SERVER_PID=<当前服务PID> MO_SERVER_LOG=<当前服务日志路径>
# 通过执行环境凭据设置 MO_PASSWORD，不把生产密码写到脚本。
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
/tmp/mo-ts-venv/bin/python run.py --setup --pilot
/tmp/mo-ts-venv/bin/python run.py --workers 4
# 按顺序执行，性能期间不要同时运行其他测试客户端：
export JAVA_HOME=<Java17路径>
/tmp/mo-ts-venv/bin/python guard.py spark.py --max-seconds 600 --max-rss-mib 4096
/tmp/mo-ts-venv/bin/python probes.py
/tmp/mo-ts-venv/bin/python guard.py performance.py --max-seconds 300 --max-rss-mib 2048
/tmp/mo-ts-venv/bin/python finalize.py
/tmp/mo-ts-venv/bin/python report.py
```

`finalize.py` 当前核对本次四个冻结源码哈希，修改程序后应为新运行重建 provenance，不能冒称原批次。`render.py` 是本工作区两个报告的 Playwright 校验脚本，另需 playwright 1.62 和 Chromium；它使用 `/workspace/mo-window-gap`，换位置需调整。完整原始包保留 SQL、结果、补测、尝试、日志、JDBC JAR；worker 主结果分片已合并到完整排序 master，不重复存放两份主输出。
