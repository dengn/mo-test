# MatrixOne 本地极端负载测试

版本：最新 main 固定提交 `2726fb419b3afa1db2686ae1b2aaca563d1ae214`；机器：4 核 CPU 配额，32 GiB 内存。

结果：共 18.5 分钟、181,794 次成功业务操作、45 次执行超时、2147 次阶段结束取消。最高并发 1024。未发生非预期进程退出或 OOM；512/1024 并发已超过这台机器可维持低延迟的处理能力。

数据：200 万行，1024 字节/行的 MD5 重复载荷（逻辑载荷 2,048,000,000 字节，可压缩），10,000 个账户。默认 CPU SIMD 构建。使用独立本地 LOG/TN/CN 实例；未修改源码。

混合负载：50% 主键查询、25% 双账户转账事务、15% 追加写入、10% 200 万行连接聚合。分析阶段为纯连接聚合，写压力阶段为 62.5% 转账、37.5% 追加写入。每次查询上限 30 秒；阶段结束取消的请求单独统计。采用闭环客户端，并发是工作线程上限，不表示恒定请求速率。

| 阶段 | 并发 | 时长(s) | 成功操作/s | 成功数 | 错误数 | 阶段结束取消 | P50(ms) | P95(ms) | P99(ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 30 | 30.57 | 917 | 0 | 1 | 1.45 | 299.10 | 320.90 |
| mixed_16 | 16 | 60 | 79.90 | 4794 | 0 | 14 | 29.63 | 1442.70 | 1694.78 |
| mixed_32 | 32 | 90 | 69.67 | 6270 | 0 | 28 | 52.76 | 3375.81 | 3876.95 |
| mixed_64 | 64 | 120 | 72.60 | 8712 | 0 | 60 | 272.12 | 5576.22 | 6180.55 |
| saturation_128 | 128 | 180 | 73.28 | 13190 | 0 | 125 | 1128.99 | 6781.93 | 8284.14 |
| overload_256 | 256 | 180 | 74.36 | 13384 | 0 | 250 | 2815.64 | 8470.75 | 10153.31 |
| analytical_pressure | 32 | 120 | 7.92 | 951 | 0 | 32 | 3923.97 | 4628.11 | 5060.54 |
| recovery | 4 | 60 | 82.27 | 4936 | 0 | 4 | 2.96 | 452.90 | 522.43 |
| overload_512 | 512 | 60 | 53.63 | 3218 | 10 | 509 | 7695.23 | 22189.71 | 23120.56 |
| overload_1024 | 1024 | 60 | 64.70 | 3882 | 35 | 1024 | 13184.14 | 26569.88 | 28894.19 |
| write_pressure_128 | 128 | 120 | 991.87 | 119024 | 0 | 96 | 115.09 | 210.72 | 271.78 |
| write_recovery | 4 | 30 | 83.87 | 2516 | 0 | 4 | 3.16 | 436.52 | 505.62 |

吞吐单位为业务操作/秒；转账包含多条 SQL。延迟分位数只计算成功操作，不涵盖超时/失败请求。阶段结束取消不计为执行错误，但代表未完成工作。

资源峰值：
{
  "peak_server_rss_gib": 6.482906341552734,
  "peak_cgroup_memory_gib": 9.92831802368164,
  "peak_server_cpu_cores": 3.993359433120067,
  "minimum_disk_free_gib": 26.285797119140625,
  "guard_triggered": false,
  "latest_memory_events": "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0"
}

数据校验：
[
  {
    "account_balance_sum": 1000000000,
    "acknowledged_events": 7861,
    "distinct_events": 7873,
    "event_attempts": 7901,
    "events": 7873,
    "item_count": 2000000,
    "item_sum_id": 2000001000000,
    "pass": true,
    "time": "2026-10-09T03:35:21.896905809Z",
    "type": "integrity"
  },
  {
    "account_balance_sum": 1000000000,
    "acknowledged_events": 53635,
    "distinct_events": 53689,
    "event_attempts": 53929,
    "events": 53689,
    "item_count": 2000000,
    "item_sum_id": 2000001000000,
    "pass": true,
    "time": "2026-10-09T03:40:09.634380035Z",
    "type": "integrity"
  }
]

错误明细：
overload_512
{
  "aggregate: context deadline exceeded": 10
}
overload_1024
{
  "aggregate: context deadline exceeded": 35
}

异常退出恢复验证：
{
  "method": "SIGKILL of own isolated mo-service, restart with same data directory",
  "readiness_seconds": 34.39521908760071,
  "verification_total_seconds": 37.574904918670654,
  "before": {
    "items": [
      2000000,
      2000001000000,
      99999000000,
      2048000000
    ],
    "accounts": [
      10000,
      1000000000
    ],
    "events": [
      53689,
      53689,
      53929
    ],
    "bad_payload_rows": 0,
    "bad_value_rows": 0,
    "accounts_sha256": "fae143c58d3135f6230bc54da7901dfcc1c9b67dc4537c4c6b3958935de57eb4",
    "events_sha256": "feb8b802b4aa1a7886852b68dec61f7659827f55057b66fbc382ee62f348e4a0"
  },
  "after": {
    "items": [
      2000000,
      2000001000000,
      99999000000,
      2048000000
    ],
    "accounts": [
      10000,
      1000000000
    ],
    "events": [
      53689,
      53689,
      53929
    ],
    "bad_payload_rows": 0,
    "bad_value_rows": 0,
    "accounts_sha256": "fae143c58d3135f6230bc54da7901dfcc1c9b67dc4537c4c6b3958935de57eb4",
    "events_sha256": "feb8b802b4aa1a7886852b68dec61f7659827f55057b66fbc382ee62f348e4a0"
  },
  "pass": true
}

服务 ERROR 日志分类（阶段结束取消会产生日志，分类不能视为独立失败请求数）：
{
  "request_cancellation": 3964,
  "transaction_commit_unknown": 30,
  "cron_trigger_mismatch": 5,
  "closed_connection": 8,
  "other": 23,
  "cron_retry_exhausted": 2,
  "background_task_fetch_error": 10,
  "success_logged_at_error_level": 5
}
第一轮降载恢复阶段前 5 秒之后的 ERROR 日志数：0。已排除内容为 upload files success 的 ERROR 级别日志；完整样本见 server-errors.json。

后台 cron 触发不匹配、重试耗尽和任务查询超时表明超载会影响内部调度；不能仅凭客户端成功判定服务完全稳定。此测试尚不能确定这些日志是否存在独立代码缺陷。

复现：加载 `source /workspace/matrixone-env.sh`；二进制 `/workspace/matrixone-latest/mo-service`；配置 `/workspace/mo-stress/config/launch.toml`；工作负载源码 `main.go`、原始结果 `results.jsonl`、资源采样 `resources.jsonl`、服务日志 `server.log`。`seed.py` 仅用于新建专用测试数据库，不应在已有库中重复执行。

测试范围为此单机、可压缩合成数据和有限时长负载；不代表多节点、真实不可压缩数据、长时间浸泡或生产容量认证。
