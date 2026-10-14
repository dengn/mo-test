# WordPress 原生回归输入

固定历史源码 `5c09ed3ccb354b0553e9b59c2876be0fc40574ca`，版本为 **7.2-alpha-64292**；不是稳定版 WordPress 的验收。完整 5,028 个 Git blob 逐个核验后复制到新的私有目录；源码内附依赖，不需要 WP-CLI。旧 wp-config.php 和未跟踪文件不会复制。GPL 许可证保留原始字节。

db.php 为原有 MatrixOne wpdb drop-in：只移除原生 options upsert 对唯一键的自赋值，保留其他原子更新；过期 transient 条件先确认值为数字再转换；DISTINCT term_id 的 ORDER BY 补选唯一键对应的名字；查询结果补回 WordPress 需要的 ID/comment_ID/comment_post_ID 大小写字段名。没有改动 WordPress 核心源码；插件查询不在认证范围。

MO_WORDPRESS_SOURCE_TREE 指向该提交的完整源码，MO_PHP_BINARY 指向现有固定 SHA 的 FrankenPHP/PHP 8.5.11。统一入口与其他 PHP 应用使用同一个 frankenphp 二进制名。每轮生成新的数据库、wp-config、认证盐、管理员密码以及订阅者密码。

原生网页安装创建表、初始数据和管理员。随后用原生密码/cookie 登录，取得 WordPress 自己的 REST nonce，通过原生 REST 创建应用密码、订阅者、分类、文章、修订和评论。Python 仅建随机数据库及读回，不插入账户、迁移记录或内容。无效浏览器 nonce、无效应用密码、匿名、订阅者写入拒绝都要求零业务写入；应用密码吊销后真实拒绝。重启停止和重新启动本轮 PHP 进程，不复用旧应用服务。

本地环境使用 WordPress 支持的 WP_ENVIRONMENT_TYPE=local，使原生应用密码能在本套件自建的 loopback HTTP 服务上使用。没有认证绕过插件。默认关闭 cron、自动核心/插件更新和文件修改，以固定本轮输入。没有认证完整浏览器界面、插件、媒体上传、多站点、已有数据升级、后台任务和负载上限。
