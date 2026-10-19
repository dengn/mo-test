# Wagtail 迁移中的失败与已知 FULLTEXT panic

原始失败全部保留，没有改写成通过，也不增加 1000 项中的已测试项目数。

| 轮次 | 结果与归因 |
| --- | --- |
| portable-round1 | 原生迁移成功，52表/207记录；测试断言误把包含已合并旧迁移的 recorder 行数等同于计划节点数。测试错误。 |
| portable-round2 | 同样完成迁移；新 fixture 漏启用 wagtail.users，后台缺用户资料表返回500。测试配置错误。 |
| portable-round3 | 修正用户应用后，53表/222记录、185计划节点全部完成，登录通过；创建草稿触发原生 FULLTEXT index INSERT 的 ReCalcNodeStats 空指针 panic。匹配 PANIC-04 / #29899，不是新问题编号。 |
| portable-round4 | 使用历史原生 fallback 搜索后端后，草稿、精确 SQL、修订 JSON 和公开API不可见通过；普通用户权限断言误要求 HTTP403，实际原生拒绝是跳回后台显示明确错误消息。测试断言错误。 |

round1/2 的原始设置见 wagtail-round1-2-settings.py；round3 的设置见 wagtail-round3-settings.py。它们只有环境引用，不含真实密码。round4 及后续使用 `modelsearch.backends.database.fallback`，这是 Wagtail/modelsearch 自带的数据库 fallback 后端，不删除已有 FULLTEXT 索引、不把该路径失败当作已修复。

在保留的 round3 原生新库中，独立诊断再次通过管理页创建合成草稿，记录 Django 实际 INSERT 模板与参数，用 PyMySQL 转义成完整 SQL。两张表来自真实 SHOW CREATE TABLE；见 [完整 SQL](wagtail-fulltext-native-panic.sql) 和 [结构化结果](wagtail-fulltext-native-panic.json)。这是源自真实原生请求的复现输入，不是重新声称该 SQL 已在当前 main 执行。触发后 SELECT1 成功，未观察到服务器进程退出。

对应已提问题：[MatrixOne #29899](https://github.com/matrixorigin/matrixone/issues/29899)。原有 cases/PANIC-04.json 继续单独保留完整 SQL、错误签名和正确值期望，并且仍要求专用实例显式开启。没有重复创建 issue，没有宣称 panic 已修复。

本次查询 main 得到候选 SHA `21f19ae06305ca2acd253d15123f851899d6b6a1`。工作盘仅几 MiB 可用，低于既有1GiB构建阈值，临时盘同时消耗接近上限的内存，因此没有启动新 main 构建或运行时；[资源门禁记录](wagtail-latest-main-admission-blocked.json) 明确标记 build_started=false、runtime_verified=false。旧 main 二进制不能冒充该提交。后续补充新数据库 issue 前仍须完成当时 main 的实际运行验证。
