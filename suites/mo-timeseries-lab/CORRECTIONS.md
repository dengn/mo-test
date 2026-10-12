# NULL 默认参数结果更正（2026-10-12）

已提交 [29925](https://github.com/matrixorigin/matrixone/issues/29925)。原研究把 `CAST(NULL AS DOUBLE)` 的“执行成功”误写成“正确通过”，未核验最后分区的 NULL 值；这个结论不准确。

三行、两个分区的最小 fixture 中，LAG 预期 `NULL,1,NULL`，LEAD 预期 `2,NULL,NULL`。无类型 NULL 默认参数各复测三次均返回 20101/index out of range panic；typed NULL 各三次分别返回 `NULL,1,0` / `2,NULL,0`，属于结果错误。省略默认参数各三次均返回正确值；显式零默认参数也各三次正确。服务仍存活，后续 SELECT 1 正常。

本次 24-query 复测记录在仓库 `research/window-gap/results/null-default-recheck-20261012.json`。原始 `results/null-default-repro.json` 的 rows 已包含最后行 0，保留原记录，修正其解释。旧脚本只断言报错次数/执行成功，新增重跑脚本同时断言完整结果及 NULL。

这两个表现均纳入 #29925。typed NULL 不能作为正确 workaround。省略默认值仅在本 fixture 验证，不外推到所有形状。

原 10,000 个主 case 的全量 MO/参考数组比对及离散/时间精确复核没有使用这个研究探针的“执行成功”断言，因此不改变 9,800 通过 / 200 高级 frame 被拒绝的计数。ClickHouse/DolphinDB 缺专用入口的 3/17 数量也不改变；这是已有 LAG/LEAD 的参数执行缺陷。

既有 ZIP 分卷、主 case 记录和来源文件保持冻结；其中“typed NULL 对照正常/保留语义”及“未新发 issue”的历史文字由本更正说明取代，不静默改写归档。
