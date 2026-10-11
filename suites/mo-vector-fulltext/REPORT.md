# MatrixOne 向量与全文极限测试实测记录

版本 main `2726fb419b3afa1db2686ae1b2aaca563d1ae214`；专用数据库 `mo_vecft_1791526357965790259`。4 核 CPU 配额、32 GiB 内存；复用前两轮的单进程 LOG/TN/CN，本轮测试脚本均位于仓库外。

## 已确认的边界

- **FULLTEXT2 陈旧缓存/延迟可见性边界，可独立复现。** 写入前查询过的表，在 CDC 尾段已经持久化后仍看不到新增文档；未提前查询的相同对照表可见新增文档。强制同步重建恢复正确。正常写入阶段 8,735 条新增源数据完整，FULLTEXT2 检索返回 0 条；源数据完整与索引可见性分别审计。见 `ft2_cache_repro.log`、`ft2_cache_repro.py`、`reproduce-ft2-cache.sql`。默认 IsStale 新鲜度扫描约每 10 分钟运行一次（cache.go 的 2.5 分钟 ticker×4），缓存繁忙时 CDC 刷新可延后；本轮数分钟内的漏检不能认定为永久损坏。本轮额外测试缩短扫描间隔，并在 finally 中恢复默认值，结果见 freshness_control.log。
- **带 WHERE 的 ANN 默认候选不足。** 默认预过滤关闭时，1% 选择性条件 `grp=99` 下 Top-10 返回 0–2 条；精确扫描返回 10 条。HNSW 执行计划先取 20 个候选再做 WHERE，单独打开预过滤开关未改善 HNSW。IVF 开启预过滤且 probe_limit=128 时，两类过滤测试均返回 10 条、召回率 100%。见 `prefilter.log` 和保存的 EXPLAIN。
- **默认 ANN 召回率不足以直接用于高召回需求。** 10 万条 128 维随机单位向量、30 个独立随机查询。每个引擎前 3 个查询用无索引 SQL 精确扫描交叉检查 NumPy 参考结果；其余以同一参考计算 Recall@10。随机球面数据是困难的合成负载，不能直接推算真实 embedding 的召回率。
- **传统 FULLTEXT 高命中评分排序在并发下超时。** 单连接相同 SQL 正确完成（约 0.09–0.79 秒），16/128 并发及混合负载出现超时。FULLTEXT2 在本轮纯全文压力阶段未出现请求错误，但默认缓存策略不提供即时读后写可见性。
- **超大 Top-K 被默认 spill 预算拒绝。** K=0/1/1000/10000 正常；K=100001 返回 `top spill disk budget exceeded ... limit=1`。源代码 `automaticSpillDiskCap` 为 LOCAL 文件系统固定保留至少 16 GiB；本环境剩余约 11 GiB，因此自动 spill cap=1 字节。该错误是资源策略与小磁盘环境的限制，不能据此宣称向量排序损坏。未为跑通测试清理旧数据或改写该配置。
- **INT8 量化带来结果和距离精度损失。** 全探测下仍非精确检索，量化索引的投影距离也可能与原始 float32 几何距离不同；原始向量源数据保持一致。克隆和 ALTER REINDEX 的对照结果见下方实测。

## 向量召回与数值误差

| 校验阶段 | 索引 | 查询数 | Recall@10 均值 | 最低值 | 最大距离绝对误差 |
|---|---|---:|---:|---:|---:|
| baseline | vh | 30 | 0.217 | 0.000 | 9.94e-08 |
| baseline | vc | 30 | 0.233 | 0.000 | 1.04e-07 |
| baseline | vi | 30 | 0.277 | 0.100 | 1.07e-07 |
| after_recovery | vh | 30 | 0.217 | 0.000 | 9.94e-08 |
| after_recovery | vc | 30 | 0.233 | 0.000 | 1.04e-07 |
| after_recovery | vi | 30 | 0.277 | 0.100 | 1.07e-07 |
| tuned | vh | 30 | 0.987 | 0.900 | 1.18e-07 |
| tuned | vc | 30 | 0.980 | 0.900 | 9.98e-08 |
| tuned | vi | 30 | 0.277 | 0.100 | 1.07e-07 |

vh=HNSW L2；vc=HNSW cosine；vi=IVF L2（128 个分区、默认本轮 probe_limit=8）。HNSW cosine 输入与查询均归一化；调优阶段采用 m=32、ef_construction=200、ef_search=1000。

IVF 全探测 `baseline`：10 个查询平均/最低 Recall@10 均为 1.000/1.000。
IVF 全探测 `after_recovery`：10 个查询平均/最低 Recall@10 均为 1.000/1.000。
IVF 全探测 `tuned`：10 个查询平均/最低 Recall@10 均为 1.000/1.000。
INT8 `initial`：平均 Recall@10 0.890，最低 0.700，最大原始距离偏差 0.052790。
INT8 `after_alter_reindex`：平均 Recall@10 0.900，最低 0.700，最大原始距离偏差 0.054193。

## 实际压力阶段

| 阶段 | 并发 | 实际秒数 | 成功操作 | 请求错误 | 操作/秒 | P99 毫秒 |
|---|---:|---:|---:|---:|---:|---:|
| vector_16 | 16 | 60.1 | 38799 | 0 | 646.0 | 139.5 |
| vector_128 | 128 | 75.3 | 41272 | 0 | 548.3 | 855.6 |
| ft_16 | 16 | 47.4 | 146 | 16 | 3.1 | 15090.1 |
| ft_128 | 128 | 72.3 | 466 | 110 | 6.4 | 43327.1 |
| ft2_16 | 16 | 45.3 | 4229 | 0 | 93.4 | 573.6 |
| ft2_128 | 128 | 62.3 | 5128 | 0 | 82.3 | 2785.4 |
| vector_1536dim_64 | 64 | 60.2 | 20883 | 0 | 347.1 | 731.6 |
| vector_fulltext_256 | 256 | 104.4 | 5079 | 200 | 48.6 | 16558.3 |
| cooldown_probe_4 | 4 | 20.0 | 108247 | 0 | 5411.2 | 3.8 |
| index_write_normal | 32 | 90.2 | 123180 | 0 | 1365.3 | 218.6 |
| index_write_crash | 32 | 150.1 | 131333 | 3330 | 875.1 | 242.2 |
| concurrent_reindex_16 | 16 | 75.1 | 93686 | 0 | 1248.0 | 40.7 |
| hnsw_tuned_16 | 16 | 45.1 | 15483 | 0 | 343.5 | 133.2 |

P99 是所有尝试的端到端延迟，包含失败、连接建立及会话初始化；15 秒是 socket read timeout，并非整个操作的统一截止时间。正常写入和故障写入阶段为 16 个跨索引事务写入者与 16 个查询者，操作数包括读操作；已确认写事务数以客户端 journal 为准。强杀窗口的拒绝连接/超时单列为注入故障的预期结果。默认 vector 阶段混合 HNSW L2/cosine/IVF 且部分 K=100；调优阶段仅 HNSW L2/cosine、K=10，因此吞吐值不能直接当成同一负载的参数前后对照。

## 正确性与恢复审计

- `before_crash`：已确认 8735，服务端 ledger 8735，缺失 0；结果不明但实际提交 0。
- `before_crash`：已确认 8735，服务端 ledger 8735，缺失 0；结果不明但实际提交 0。
- `after_crash`：已确认 18981，服务端 ledger 18983，缺失 0；结果不明但实际提交 2。
- `after_maintenance`：已确认 18981，服务端 ledger 18983，缺失 0；结果不明但实际提交 2。
- `after_concurrent_reindex`：已确认 18981，服务端 ledger 18983，缺失 0；结果不明但实际提交 2。
- `final`：已确认 18981，服务端 ledger 18983，缺失 0；结果不明但实际提交 2。
- `before_crash` 全源数据核对：`{"vhm": [[8735, 0, 0]], "vim": [[8735, 0, 0]], "ftm": [[8735, 0, 0]], "ft2m": [[8735, 0, 0]]}`；每个数组依次为 ledger 行数、缺失行数、源向量/文本不一致数。
- `after_crash` 全源数据核对：`{"vhm": [[18983, 0, 0]], "vim": [[18983, 0, 0]], "ftm": [[18983, 0, 0]], "ft2m": [[18983, 0, 0]]}`；每个数组依次为 ledger 行数、缺失行数、源向量/文本不一致数。
- `after_maintenance` 全源数据核对：`{"vhm": [[18983, 0, 0]], "vim": [[18983, 0, 0]], "ftm": [[18983, 0, 0]], "ft2m": [[18983, 0, 0]]}`；每个数组依次为 ledger 行数、缺失行数、源向量/文本不一致数。
- `after_concurrent_reindex` 全源数据核对：`{"vhm": [[18983, 0, 0]], "vim": [[18983, 0, 0]], "ftm": [[18983, 0, 0]], "ft2m": [[18983, 0, 0]]}`；每个数组依次为 ledger 行数、缺失行数、源向量/文本不一致数。
- `final` 全源数据核对：`{"vhm": [[18983, 0, 0]], "vim": [[18983, 0, 0]], "ftm": [[18983, 0, 0]], "ft2m": [[18983, 0, 0]]}`；每个数组依次为 ledger 行数、缺失行数、源向量/文本不一致数。
- 全文增量 `before_crash`，等待 60.6s：`{"ftm": {"found": 8735, "missing_ledger": 0, "extra": 0, "pass_check": true}, "ft2m": {"found": 0, "missing_ledger": 8735, "extra": 0, "pass_check": false}}`。
- 全文增量 `after_crash`，等待 60.0s：`{"ftm": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}, "ft2m": {"found": 11199, "missing_ledger": 7784, "extra": 0, "pass_check": false}}`。
- 全文增量 `after_maintenance`，等待 0.2s：`{"ftm": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}, "ft2m": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}}`。
- 全文增量 `after_concurrent_reindex`，等待 0.1s：`{"ftm": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}, "ft2m": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}}`。
- 全文增量 `final`，等待 0.2s：`{"ftm": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}, "ft2m": {"found": 18983, "missing_ledger": 0, "extra": 0, "pass_check": true}}`。
- 更新/删除可见性：`{"kind": "delete_update_visibility", "epoch": 1791527967.44707, "seconds": 60.78989083799934, "result": {"ftm": {"changed_count": 100, "original_count": 800, "pass_check": true}, "ft2m": {"changed_count": 0, "original_count": 900, "pass_check": false}}}`。
- 同步重建后的更新/删除校验：`{"ftm": {"changed_count": 100, "original_count": 800, "pass_check": true}, "ft2m": {"changed_count": 100, "original_count": 800, "pass_check": true}}`。
- `vhm` 增量 ANN 已确认 ID 采样 30 个，未找到的精确 ID：`[1100000228]`。K 至少 64 且大于同源向量行数，避免重复向量掩盖缺少 posting。
- `vim` 增量 ANN 已确认 ID 采样 30 个，未找到的精确 ID：`[]`。K 至少 64 且大于同源向量行数，避免重复向量掩盖缺少 posting。
- `vhm` 增量 ANN 已确认 ID 采样 30 个，未找到的精确 ID：`[]`。K 至少 64 且大于同源向量行数，避免重复向量掩盖缺少 posting。
- `vim` 增量 ANN 已确认 ID 采样 30 个，未找到的精确 ID：`[]`。K 至少 64 且大于同源向量行数，避免重复向量掩盖缺少 posting。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528152.0263965, "table": "vhm", "id": 1100000228, "source_id": 229, "k": 64, "found": false, "distance_zero_rows": 0, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528152.0343034, "table": "vhm", "id": 1100000228, "source_id": 229, "k": 128, "found": false, "distance_zero_rows": 0, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528152.0581324, "table": "vhm", "id": 1100000228, "source_id": 229, "k": 256, "found": true, "distance_zero_rows": 17, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528152.0954092, "table": "vhm", "id": 1100000228, "source_id": 229, "k": 1000, "found": true, "distance_zero_rows": 17, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528319.7796566, "label": "tuned_mutable", "table": "vhm", "id": 1100000228, "source_id": 229, "k": 10, "found": true, "distance_zero_rows": 10, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528319.7853353, "label": "tuned_mutable", "table": "vhm", "id": 1100000228, "source_id": 229, "k": 64, "found": true, "distance_zero_rows": 17, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528319.7904053, "label": "tuned_mutable", "table": "vhm", "id": 1100000228, "source_id": 229, "k": 128, "found": true, "distance_zero_rows": 17, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 重复向量召回对照：`{"kind": "duplicate_ann_control", "epoch": 1791528319.7958033, "label": "tuned_mutable", "table": "vhm", "id": 1100000228, "source_id": 229, "k": 256, "found": true, "distance_zero_rows": 17, "same_source_rows": 17}`。源数据中该 ID 的精确距离为 0；默认 K=64/128 时未召回整个同源组，K=256 时召回全部 17 个，说明这是 ANN 候选/召回边界，不能当成 posting/源数据丢失。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528311.7223036, "label": "default_after_durable_cdc", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528311.732164, "label": "shortened_cadence", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528312.7379985, "label": "shortened_cadence", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528313.743189, "label": "shortened_cadence", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528314.7480483, "label": "shortened_cadence", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528315.7522967, "label": "shortened_cadence", "fulltext_result": [], "fulltext_new_visible": false, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_control", "epoch": 1791528316.768253, "label": "shortened_cadence", "fulltext_result": [[2]], "fulltext_new_visible": true, "hnsw_new_id_visible": true}`。
- 缓存间隔控制：`{"kind": "freshness_convergence", "epoch": 1791528316.7684255, "seconds": 5.041808958998445}`。
- 缓存间隔控制：`{"kind": "freshness_restored", "epoch": 1791528316.7697783, "result": [["{\n  \"method\": \"SETVECTORINDEXFRESHNESSINTERVAL\",\n  \"result\": \"applied=[127.0.0.1:18002:0]\"\n}\n"]]}`。

SIGKILL 后 SQL 就绪时间 35.15s；等待 POSIX/flock 文件锁释放 0.217s，再启动服务，避免前轮已观察到的立即重启锁冲突。这是带锁释放等待的测试脚本恢复时间，并非无人介入的自动故障转移。故障发生时累计 11306 次客户端确认。

## 数据、覆盖范围与限制

- 每个主向量索引 100,000 行×128 维；三种索引和一个无索引参照表。另有 5,000 行×1,536 维、65,535 维单行边界、INT8 量化及克隆表。
- 两种主全文引擎各 60,000 篇文档，8 种可枚举的英文词/短语组合，每篇重复 20 次以扩大 posting/评分压力。另有中文 ngram/gojieba、23 字节词长截断、Unicode 扩展折叠、空/NULL、63,000 字节重复词文档、JSON_VALUE 多列空字段案例。
- 覆盖 NaN/Inf、维度不匹配、数值溢出、零/极小 cosine 查询、坏数据批量插入原子性、LIMIT 0/超大 LIMIT、派生表聚合、选择性过滤、事务写入、更新/删除、量化重建和克隆、检索期间同步重建/合并、活跃写入期间强杀。
- 原始 FULLTEXT 布尔 membership、FULLTEXT2 精确短语及中文 membership 使用全集合对照。向量源内容用无索引 join 的距离逐行核验；早期增量 ANN 校验只检查 20 个点的零距离，存在重复向量掩盖 posting 缺失的局限。最终追加按已确认 ID 的 30 点校验并提高 K 以覆盖同源向量；这些采样仍不能证明每个 ANN posting 都完整。
- 早期脚本尝试 INT 主键 HNSW、超长 TEXT 和向量转 VARCHAR，触发了约束/不支持错误；随后修正测试构造，保留初始日志。这些不是大量独立服务缺陷。极小 cosine 输入在本构建的标量和列路径返回数值正确结果，早期“应该拒绝”的断言已按实测精度核正。
- 合成数据、本机客户端与服务共用 CPU、单进程部署、短时阶段，不代表多节点高可用、GPU/CAGRA 或数天 soak 测试，也不证明长期无泄漏。

## 资源观测

`{"server_rss_gib": 4.924007415771484, "cgroup_memory_gib": 10.718013763427734, "disk_free_min_gib": 10.822925567626953, "goroutines": 2270.0, "resource_guard_triggered": false, "memory_events_last": "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0"}`

内核 OOM 计数与资源阈值监控见 resources.jsonl。ERROR 日志包括注入取消、输入拒绝、后台事务重试以及被错误级别记录的 upload files success；不能把 ERROR 行数直接当成独立故障数。完整分组见 summary.json。

## 复查命令与证据

所有脚本和结果保留在 `/workspace/mo-vector-fulltext`。`database.txt` 指向本轮数据；不删除前两轮数据库。可复查当前数据：

```bash
OPENBLAS_NUM_THREADS=1 /workspace/toolchains/python/bin/python /workspace/mo-vector-fulltext/suite.py oracle review
OPENBLAS_NUM_THREADS=1 /workspace/toolchains/python/bin/python /workspace/mo-vector-fulltext/mutation.py audit review
```

`reproduce-ft2-cache.sql` 在一个新专用数据库中运行；其中 readiness 必须等两列均为 1 后再执行 MATCH。`ft2_cache_repro.py` 自动完成同样的 durable-tail 对照；其现有测试表已保留，重新执行需使用新的表名。

原始结果：results.jsonl；阶段日志：stress.log、index-write-crash.log；详细控制：prefilter.log、query_boundaries.log、fulltext_controls.log、quantization.log、ft2_cache_repro.log、freshness_control.log；恢复：crash-recovery.json；资源：resources.jsonl；机器可读汇总：summary.json；最终检查：verification.json。
