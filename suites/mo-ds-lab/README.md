# MatrixOne 数据科学兼容性测试

当前测试对象是工作区现有的 `mo-service`，编译自 commit
`23d8f61252f3017dff218b530817a240206fd762`。不要将工作区源码 HEAD
`dd38098853ea197699ed3fac3e69dc53975ac061` 当作运行二进制的版本。

## 用例计数

主批次恰好 100,000 个带唯一 case_id 的参数化断言，不代表 100,000 种算法：

|工具|模板|参数数|断言数|执行粒度|
|---|---:|---:|---:|---|
|Pandas|49|1000|49,000|每例独立执行 SQL，SQLAlchemy + read_sql_query|
|NumPy|49|1000|49,000|每例独立执行 SQL，PyMySQL 取回结果|
|Spark|10|100|1,000|10 个 JDBC 读/聚合/写 pipeline，每个 100 个独立 group|
|Flink|10|100|1,000|10 个 JDBC 读/聚合/写 pipeline，每个 100 个独立 group|

NumPy 不提供数据库驱动，此处用 PyMySQL 连接，以 NumPy 计算独立期望值。
Pandas 的期望值使用 Series/DataFrame；适用的数学函数调用 NumPy。
两套 oracle 在执行前相互核对。期望值来自确定性生成的数据，不从数据库
返回结果推导。浮点容差为 relative/absolute 各 `1e-7`；整数断言亦按此
容差比较（本次整数值范围内不会接受单位整数差异）。每 10 个参数中有
1 个返回空集，验证 COUNT=0、其他聚合=NULL 的语义。

Spark 默认 pipeline 的 100 个 group 如因共享 SQL/JDBC 步骤失败，100 个
case 均记录 `pipeline_error`，不得解读成 100 个独立根因。补测与配置修复
放在独立目录，不覆盖主批次失败。

## 重跑

本环境 Python 位于 `/workspace/mo-ds-venv/bin/python`。依赖版本、JAR 校验和
及运行二进制的构建信息分别见 `requirements-lock.txt`、`jars-sha256.txt`、
`binary-build-info.txt`。虚拟环境复用了基础环境的 Pandas 2.2.3、psutil 等
包；`requirements-lock.txt` 是新增本地依赖，完整版本见结果 metadata。

连接参数可用 MO_HOST、MO_PORT、MO_USER、MO_PASSWORD、MO_DATABASE 配置。
默认只适用于本地隔离测试实例（127.0.0.1:6001，MatrixOne 默认测试账号），
生产账号请通过环境配置注入。创建的测试库为 ds_validation_20261011。
脚本会重置本测试库中的 output、边界测试、计数器表，应仅在专用库运行。

```bash
cd /workspace/mo-ds-lab
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/mo-ds-venv/bin/python run_core.py
SPARK_LOCAL_IP=127.0.0.1 /workspace/mo-ds-venv/bin/python run_connectors.py spark
/workspace/mo-ds-venv/bin/python run_connectors.py flink
SPARK_JDBC_ISOLATION=READ_COMMITTED SPARK_LOCAL_IP=127.0.0.1 \
  /workspace/mo-ds-venv/bin/python run_connectors.py spark --out results/spark-read-committed
/workspace/mo-ds-venv/bin/python run_supplemental.py
/workspace/mo-ds-venv/bin/python run_supplemental.py --bench-only
/workspace/mo-ds-venv/bin/python summarize.py
```

本地服务配置在 config/，数据在 mo-data/，server.pid 用于监控同一个进程。
启动命令（在 MatrixOne 工作目录运行，使用新的专用数据目录）：

```bash
source /workspace/matrixone-env.sh
cd /workspace/matrixone
nohup ./mo-service -launch /workspace/mo-ds-lab/config/launch.toml \
  > /workspace/mo-ds-lab/server.log 2>&1 &
echo $! > /workspace/mo-ds-lab/server.pid
```

不要复用旧的 mo-data。本次 onboarding 旧目录启动出现 shard not bootstrapped，
该环境启动问题不计入 10 万例兼容性失败。

## 范围与限制

这是 4 核 CPU 配额、16 GiB 内存的同机单节点测试，未比较其他数据库、
未测试远端网络、分布式部署、故障恢复、长时间运行或生产容量。
主批次表有 8192 行，JDBC 表有 6400 行。它们用于兼容性，不代表大数据
性能。百万行性能表为 1,048,576 行，三个混合查询负载分别为全扫描统计、
分组聚合及过滤点积；性能补测记录热缓存客户端 query+fetch 时间。
核心批次后段与初次 Spark 验证有时间重叠，其延迟仅是观察值。
最终百万行测量时核心、Spark/Flink 和事务 soak 均已结束。首档测量初期
额外执行了两条短向量语义复核查询，其余测量没有额外测试负载。

稳定性补测为 120 秒、8 线程、各自操作独立计数器行，验证提交、回滚和
读回值；不证明热点争用、线性一致性、分布式容错或长期稳定性。
客户端计算与 MO 下推计算在结果中明确分开：Spark/Flink 聚合由各引擎
执行，NumPy/Pandas oracle 在客户端执行，不能把这些耗时当成 MO 内核耗时。

Flink JDBC 4.1.0-2.1 需要 core、mysql、OpenLineage SQL/Java 及 MySQL driver
JAR。首次缺 OpenLineage 的尝试保存在 results/flink-setup-first/；它是客户端
依赖配置问题，排除在主批次数据库兼容性结果外。

请保留 report.json、原始 JSONL、query SQL 和 error 字段。主批次
`case_id` 必须恰好覆盖 [0,99999] 且无重复；summarize.py 会验证该条件。
