此目录汇总 MatrixOne 500,000 个测试实例的报告和重放入口。

原始包：

- `/workspace/mo-cases-50000`：文档、MySQL 公开测试、MatrixOrigin 仓库来源。
- `/workspace/mo-chaos-50000`：复杂 SQL、混合负载、取消查询、断连回滚和 5 次 SIGKILL 恢复。
- `/workspace/mo-crossdb-100000`：Doris、StarRocks、TiDB、ClickHouse、TDengine、Milvus 的场景映射。
- `/workspace/mo-etl-100000`：Snowflake、Fivetran、dbt 的接入、转换、增量、快照、导出场景映射。
- `/workspace/mo-gap-200000`：完成前 300,000 个后依据覆盖审计追加的约束、SQL、类型、向量和并发边界。

每包提供 `cases.jsonl`、`coverage.json`、`source-manifest.json`、`runner.py`、`results.jsonl`。原始结果保留，不将重复执行、校准或最小复现加入主测试计数。参数化实例不等于 500,000 种独立功能，全文/向量的浮点或近似检索边界也不自动等于缺陷。

查询类单个实例重放：

```bash
/workspace/toolchains/python/bin/python /workspace/mo-stability-500000/replay_case.py C47965
```

带状态的写入、导入和快照实例依赖初始数据；使用新的独立数据库完整重放：

```bash
/workspace/mo-stability-500000/run_all.sh
```

完整重放包括 5 次主动 SIGKILL，仅针对已记录 PID 的本地 `mo-service` 测试实例。运行前保留服务数据、旧结果和日志；数据在同一测试实例的独立数据库中。脚本使用 `MO_SUITE_DATABASE` 隔离此次重放，结果文件也使用该数据库名。MySQL 8.0.46 对照容器只开放 `127.0.0.1:63306`。

未启动 Snowflake/Fivetran SaaS 服务，也未部署 Doris/StarRocks/TiDB/ClickHouse/TDengine/Milvus；对应批次测试的是公开文档场景在 MatrixOne 中的实现。Fivetran 消息、dbt 增量与 SCD2 使用显式 SQL 模拟；dbt adapter 本身未验证。物理分区裁剪、专有引擎布局、自动物化、流处理平台等不能仅由 SQL 结果证明。
