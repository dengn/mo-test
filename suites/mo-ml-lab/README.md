# MatrixOne 深度机器学习管线实验

本目录包含真实连接 MO 的 20,000 个主批次 case（20 个模型/任务模板 × 1,000 个参数配置），以及单独统计的 200 个 Spark worker 深度训练、20 个嵌在这些流程中的 Spark 原生 ML 管线和 100 个混合网络工作流。性能批次为另计的 240 次测量。最终完成情况以 `report.json` 为准；启动或生成目录不代表运行成功。

训练在 CPU PyTorch / Spark 中执行；MO 承担多表数据、特征、模型二进制与预测存储。数据完全合成，不涉及生产数据。结果针对实际二进制提交 `23d8f61252f3017dff218b530817a240206fd762`，不是工作区较新的源码。机器资源为 4 CPU / 16 GiB。

## 学习任务与数据

16 张源表共 142,163 行：实体、观测、干净目标、交易、维护、故障、天气、日历、价格、暴露、行业、策略、事件、干预、图边及标签。包含重复实体每日交易、稀疏事件、缺失值、异常信号和时点维护记录。宽表取数包含 CTE、22 个 JOIN 关键词、相关 NOT EXISTS 和 LAG 窗口；这是 SQL 文本计数。

主批次架构为残差 MLP、时序 CNN、多层 GRU、多块注意力和 GCN；各运行预测、风险分类、多任务、监督去噪四项任务。网络宽度 8–20，块/层数 2–5，序列 6–12，训练 8–14 个 epoch，组合实体范围、预测 horizon、时间锚点、缺失/噪声、batch、学习率、L2 与梯度裁剪。共有 1,000 条不同事实 SQL，20 个任务共享这些事实设计，但每一个 case 都重新读取 MO 并训练。

40 个训练实体、12 个验证实体、12 个测试实体互不重叠。训练标签时间早于验证特征锚点，验证标签时间早于测试锚点。填充、标准化和目标缩放只拟合训练集；图传播只允许分区内的边。未来标签不进入特征列。监督去噪使用已知合成干净信号，不能把它称作无监督异常检测。

不同配置的留出实体可以重叠；case 数量表示管线配置覆盖，不等价于独立业务样本量。预测表和逐 case 记录保存模型原始头输出：预测任务为标准化响应，分类为风险 logit，多任务为二者，去噪为四维标准化干净信号。测试质量指标已还原到相应尺度。

## 实际核验

1. MO 全量 29 列事实逐行与原始源表独立重建的 pandas 参照比对，`rtol=atol=1e-8`，发生在 float32 模型输入转换之前。
2. 训练/验证/测试实体与标签时间间隔、训练集填充/标准化、测试标签扰动、图分区、有限梯度、非零更新及训练损失下降。
3. MO 特征与独立参照分别执行确定性 PyTorch 训练，完整权重、所有推理值和训练历史要求完全相等。这一项复用同一模型算法，独立的是数据构建和实际训练运行。
4. 五类模型另有手写 NumPy 前向实现，与 PyTorch 按 `rtol=atol=3e-5` 核对，区别来自 float64 / float32 运算。报告保留实际最大误差；该容差不用于原始事实核对。
5. 模型 checkpoint、分类阈值及预测区间残差分位数只使用验证集。允许验证集选回初始 checkpoint，报告会明确计数；不把兼容性通过解释为所有模型都有更好的测试质量。
6. 写回实际选中的模型 state 和全部 12 个测试预测，读回完整二进制/元数据/预测，`weights_only=True` 重载，推理要求逐位相等。每个 case 在另一个连接验证提交或回滚可见性，随后清理专用结果表。模型二进制全部另存于 `models/00000.pt` 至 `models/19999.pt`，逐个核对 SHA256。
7. 源表主批次前后及最终全量内容和哈希保持一致；专用结果表最终为空；监测服务 PID、RSS、健康探测及 cgroup OOM 事件，单独分析后台日志。

Spark 补充流程全量核对 JDBC 导入的 16 张源表，执行等价 Spark SQL，并将 10 条特征 SQL 直接经 MO JDBC 执行。20 个原生 ML 管线包含 VectorAssembler、训练集 StandardScaler、PCA 和回归/分类，另用 NumPy 检查统计量、正交性、解释方差及系数推理。200 个深度模型在真实 Python worker 中训练，实际 worker 权重及预测经 Spark JDBC 写回/读回，重载一致。

混合网络将 3 CNN、2 GRU、3 注意力块、3 图卷积及多头串联，运行未来预测/风险/掩码重构/有序分位数，同时做 24 次 MC dropout、12 步积分梯度和 8 步 PGD。检查可重复性、有限值、分位数次序与扰动边界，不声称证明鲁棒性、解释完备性或达到真实业务准确率。

## 重跑

建议复制代码到新目录并使用新测试库，保留本批次冻结文件及结果。需要 Python 3.12、对应 `requirements.txt`，CPU 版 PyTorch、Java 17 和包内的 MySQL JDBC jar。安装时保留环境中的代理和 CA 设置。通过环境变量配置 `MO_HOST`、`MO_PORT`、`MO_USER`、`MO_PASSWORD`、`MO_ML_DATABASE`；仅对专用合成测试库执行写入。

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export MO_ML_DATABASE=ds_ml_replay
python data.py
python run.py --pilot
python run.py
export JAVA_HOME=/path/to/java17 SPARK_LOCAL_IP=127.0.0.1
python guard.py spark.py --max-seconds 2400 --max-rss-mib 5120
python compound.py
python performance.py
python serving_check.py
python finalize.py
python capture_trace.py
python export.py
python plot.py
python report.py
```

冻结的 `run.py` 监测本机服务 PID 1384；`finalize.py` 的二进制、日志及 cgroup 路径也对应本实验机器。移到另一机器时，应在新副本调整这些监测路径/PID，保留原始执行文件不动。JDBC jar 可由 `MO_JAR_DIR` 指定。Spark 使用 `READ_COMMITTED`，并在主批次结束后串行执行；性能测量也必须没有其他测试客户端并发运行。

逐 case 重放原批次留存模型：

```bash
python replay.py 14999
python replay.py 14999 --offline
python replay.py 14999 --offline --retrain
python serving.py 14999 --offline
```

在线重放使用该 case 的事实 SQL 重新读取 MO；离线重放使用完整 CSV 导出并比对确定性源数据。两者都检查特征哈希、模型哈希、全部推理哈希、12 个留出预测及 NumPy 前向。仅在 `--retrain` 时重新训练。`serving.py` 另使用 `preprocessing.json` 的已保存参数，先剥离全部标签列，推理阶段不拟合任何统计量，也不向模型传入真实标签；同样要求输出逐位相等。完整重跑时，在 `serving_check.py` 前用 `python serving.py --export` 生成这份参数。`serving_check.py` 对同一批 20,000 个模型做部署阶段全量复核，不计为新增训练 case。

## 统计与已知限制

`cases.jsonl` 是主批次唯一 20,000 条原始记录，`cases.csv` 便于筛选；`spark-cases.jsonl`、`compound-cases.jsonl`、`performance-cases.jsonl` 分开。140 个试跑和 `attempts/static-scheduling/` 中因负载分配不均而中止的 1,079 个完成 case 不计入正式批次。中止仅针对测试客户端，MO 服务保持运行。

Spark 默认 JDBC 隔离级别兼容问题已有 [#29838](https://github.com/matrixorigin/matrixone/issues/29838)，本批次明确配置 READ_COMMITTED。后台 `statement_info` TEXT 65535 容量问题与 [#29809](https://github.com/matrixorigin/matrixone/issues/29809)、[#29797](https://github.com/matrixorigin/matrixone/issues/29797) 有关；窗口内可能重试旧 ETL 文件。日志上下文条数、失败内部 LOAD 次数和业务 case 失败分别统计；不据此断言永久丢失或重试已经恢复。

`attempts/spark-worker-python/` 保留首次 Spark 客户端启动失败：direct-driver 的 worker 默认使用系统 Python，缺少 PyArrow。最终批次明确设置 `PYSPARK_PYTHON` / `PYSPARK_DRIVER_PYTHON` 为测试虚拟环境，并从头完成 200 个 case。`serving-layout-finding.json` 记录另一项客户端重放差异：相同输入采用不同内存布局出现约 4.3e-7 的浮点差异；通过统一 C-contiguous float32 布局恢复逐位相等，未放宽容差。

性能是完整 ML 工作流（取数、预处理、一次训练、模型/预测写回、重载及事务检查），不是 MO 纯 SQL QPS。单次计时之外做预计算参照比对，批次吞吐仍包含这些检查、进程和连接开销。主批次耗时包含两次训练和全部核验，不用于衡量纯训练速度。小型合成 CPU 网络不能代表大模型、GPU 扩展、生产负载或真实业务准确率。
