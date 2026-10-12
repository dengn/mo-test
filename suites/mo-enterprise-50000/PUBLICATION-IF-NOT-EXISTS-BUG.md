# CREATE PUBLICATION IF NOT EXISTS 仍然报重复键

固定 MatrixOne main 提交 2726fb419b3afa1db2686ae1b2aaca563d1ae214，sys/root，通过普通 MySQL 协议发送 SQL。两次相同 CREATE 中，第一次成功，第二次报 1062：

~~~sql
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
-- Duplicate entry '(0,e2e_pub_idem)' for key '(account_id,pub_name)'
DROP PUBLICATION IF EXISTS e2e_pub_idem;
~~~

完整原始记录在 publication-idempotence-recheck.json；初始测试配置阶段也遇到同样现象。专用 pub50 库及 visible 表由 setup.py 准备。

IfNotExists 被解析进 AST，但 pkg/frontend/publication_subscription.go 的创建路径没有使用该标记检查已存在的 publication。本次没有修改产品代码。

该问题属于 DDL 幂等语义，不是 1,000 条相同错误计作 1,000 个 bug；主批次的发布订阅读取、权限与只读检查单独计数。
