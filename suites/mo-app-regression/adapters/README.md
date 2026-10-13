# 原生应用适配源代码

`documize_mysql_adapter.py` 是本次 Documize v5.14.0 官方二进制实跑使用的适配器源码。只在隔离测试环境使用，监听 loopback 临时端口并连接实际 MatrixOne 6001；原生客户端认证和服务器响应直接转发。审计路径包含原始/适配 SQL，必须私有。仅针对已观察到的 Documize SQL 形状改写，不是通用 SQL 网关。

适配包含已有唯一非空 search.id 的主键、固定 NVARCHAR 宽度、config 表名及 subscription 结果别名的引用、JSON 默认值类型、真实 DDL COMMIT 边界。七个 MySQL ENGINE 切换和一条 OPTIMIZE 被显式省略并执行真实 COMMIT/表存在查询；不代表完成引擎转换或压缩。旧版 main 与稳定版需要这些适配，最新 main 的部分限制已有修复，仍需运行时决定哪些适配保留。

Documize 独立驱动现已实现为 run_documize.py，新建库原生初始化和 25 项验证通过；适配器模块本身不另计为应用。业务/负载/失败证据见 [源仓库历史证据](https://github.com/matrixorigin/matrixone-app-regression/tree/e3f59736522ec3128cc47b541d292fafc6dcfbd1/evidence)，完整 fixture/账号仍在当前隔离环境，公开仓库不包含密码/JWT。
