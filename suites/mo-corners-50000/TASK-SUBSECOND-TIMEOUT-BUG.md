# 正数小于 1 秒的 task timeout 被静默关闭

三个独立 task 的同一 INSERT ... SELECT SLEEP(2) 对照：

|配置|存储 timeout_seconds|执行结果|写入行数|
|---|---:|---|---:|
|100ms|0|约 2.37 秒后 SUCCESS|1|
|1s|1|约 1.09 秒后 TIMEOUT|0|
|3s|3|SUCCESS|1|

原始 SQL、状态、耗时及写入记录见 task-timeout-recheck.json 和 task-timeout-recheck.log。create task 接受 100ms 且不告警；用户给出的正数限制转成了关闭限制。

pkg/taskservice/sql_task_utils.go: ParseSQLTaskTimeout 返回 int(d / time.Second)，将正数不足 1 秒截成 0；sql_task_executor.go 仅在 TimeoutSeconds > 0 时设置 deadline。1s 的正常超时及回滚与仓库已有 SQL 回归用例一致，未把它误计为失效。

原始 task-scheduler-e2e 记录中 timeout 期望 FAILED 是测试预期错误，规范状态应为 TIMEOUT；3 秒内等待 resume 的结果也不足以证明后台调度失效，需按调度轮询周期复核。这些原始记录保留，不把误判计入缺陷数。
