# Huginn 稳定版实验适配

固定源码 d6f25e28a36f360ad80c73445c3ce5229be7e538（MIT，867 Git blob 核对通过），实际目标 MatrixOne v4.2.5。这里只保存本轮验证所用配置和迁移源代码，不是第五个独立 CI 应用驱动。

`database.yml` 使用 Rails 支持的变量配置，保留原生 strict:false 对有效 SQL 模式的处理，移除其字符串拼接产生的空模式项；wait_timeout 显式设为服务器接受的 86400。

`set_charset_for_mysql.rb` 的 MatrixOne 分支省略稳定版 CHANGE 不支持的字符集/排序规则属性，保留列类型、长度、空值、默认值及原生索引。另显式省略不受支持的 MySQL ALTER DATABASE 默认字符集切换，保留隔离库 utf8mb4 默认。大小写不敏感排序/唯一性、其他字符集和已有数据升级的一般等价性未经验证；不要作为全功能兼容保证。

73 个原生迁移、原生账号 seed、原生场景导入、25 项 HTTP/异步工作流/权限/重启检查均实跑完成。原始失败记录保留，浏览器错误密码页面200、原生数组 null 清除、保留周期7不合法是已纠正的测试假设，不当作数据库错误。原生重启验证包含未在55秒内退出而强制结束的进程，不证明优雅停机。高负载因磁盘余量未获准进入，零请求不计作压力通过。

源码 SHA、native npm/Ruby 锁文件身份、SDK 包 SHA、原始 SQL 及失败/成功证据见 [源仓库历史证据](https://github.com/matrixorigin/matrixone-app-regression/tree/e3f59736522ec3128cc47b541d292fafc6dcfbd1/evidence)。两个新增 SQL 回归用例在稳定版已匹配失败并通过值/约束对照；最新 main 运行验证尚未完成，未为本轮错误提交新 issue。依赖和账号原始状态留在当前隔离环境，密码和令牌不包含在仓库。
