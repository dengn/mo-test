# Backend 日志核查与 issue 检索

主批次 20,000、Spark 200、混合模型 100 个完整训练工作流全部通过；同一批 20,000 个模型的无标签部署重放及 240 次性能测量也通过。源表全量内容保持一致，19 张专用结果表为空，711 次主批次健康采样错误为零，未发现 panic/fatal 或 cgroup OOM。以下是日志上下文，不能直接当作失败业务 case 数。

固定日志窗口有 1,778 条 ERROR：1,673 条 statement_info TEXT 容量上下文、82 条上传批次零成功摘要、4 条表统计任务上下文，以及 3 条前端会话上下文和 16 条 join 依赖中断上下文。

内部 trace LOAD 失败记录 398 次，ETL 失败上传记录 398 条，对应 375 个不同的文件；这些文件的文件名生成时间均早于主批次起点。没有找到本窗口内生成的失败文件，因此 `telemetry-analysis.json` 没有当前主批次的超长记录样本。不能把旧队列重试全部归因于新 ML case，亦不能推断永久丢失或重试已恢复。相关既有 issue [#29809](https://github.com/matrixorigin/matrixone/issues/29809)、[#29797](https://github.com/matrixorigin/matrixone/issues/29797) 仍为 open。

前端会话记录在 2026-10-11 15:49:22 UTC：一条 `cannot process request as routine is closed or busy`，以及同一错误 SHA256、67 字节、moerr-code 20101 的 handling/read 上下文两条。日志不含足够的 SQL/session 关联，无法定位到具体 case 或确认是否为正常连接清理；所有被测客户端的业务返回与读回核验均通过。全局 occurrence/suppressed 计数不能当作本批次新增失败数。同文案检索命中已关闭的 [#20022](https://github.com/matrixorigin/matrixone/issues/20022)，但其场景是 proxy cached connection 下的服务 hang；本批次为单机直连且未 hang，尚不能认定为同一个问题。

16 条 `query interrupted` 的 caller 为 `message/joinMapDependency.go:344`，发生在两轮 Spark 客户端运行的时间范围内。实际二进制提交 `23d8f61252f3017dff218b530817a240206fd762` 的该路径在将非 deadline 的 context 错误转换为独立 typed moerr 时构造 `NewQueryInterrupted`。这解释了日志组件，未证明哪一条请求被取消或取消是否为正常清理。组件名检索命中已关闭的 [#27646](https://github.com/matrixorigin/matrixone/issues/27646)、[#27524](https://github.com/matrixorigin/matrixone/issues/27524)，涉及取消包装和分布式写入外键错误覆盖，尚无本测试触发条件相同的已确认 issue。

完整原始上下文在 `frontend-log-contexts.json`、`error-samples.json`、`server-canonical.log`，搜索结果在 `github-frontend-search.json` / `github-join-dependency-search.json`。没有依据这些未归因的日志自动新发 issue。Spark 默认 JDBC 隔离级别问题 [#29838](https://github.com/matrixorigin/matrixone/issues/29838) 仍为 open，本批次明确配置 READ_COMMITTED。
