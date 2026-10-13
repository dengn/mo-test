# 新迁移驱动的运行环境

所有账号、应用密钥、测试库、初始化和业务数据由每次驱动重新生成。这里的 SDK 是可复用的源码、编译器、依赖和原生二进制，不包含旧业务库或账号。当前驱动不自动修改系统软件或下载未固定版本的包。

## Documize

驱动可自动下载官方 v5.14.0 Linux amd64 二进制，并检查固定 SHA / 字节数；也可传 `--binary`。只用 Python 标准库与 PyMySQL，MySQL 适配器跟随本次驱动启动/停止，目标来自 MO_HOST/MO_PORT。它保留原生密码、JWT、响应和迁移，显式省略 MySQL 物理 ENGINE / OPTIMIZE，不能据此声称完成转换或压缩。

## Huginn

使用 Ruby 3.4.11、Bundler 4.0.8、固定 d6f25e28 源码、原始 Gemfile/Gemfile.lock，以及按原锁文件准备的 production bundle 和编译好的 native assets。SDK 安装依赖 Ruby/OpenSSL/libyaml/zlib/MySQL 客户端开发库及 Node 24；冷准备需要充足的磁盘和编译环境。本轮使用已有 SDK，没有在另一台机器重新安装全部依赖。

复制 [运行配置示例](fixtures/huginn/runtime-config.example.json) 到 SDK 目录，填写 source_tree、ruby_binary、bundle_binary、gem_home、bundle_path、assets_dir、native_library_dirs。路径相对该 JSON 文件解析，亦可用绝对路径；JSON 只存路径，不存密码。`MO_HUGINN_RUNTIME_CONFIG` 或 `--runtime-config` 指向它。

```bash
python run_huginn.py --runtime-config /path/to/sdk/runtime-config.json \
  --out artifacts/huginn-001
```

驱动校验 867 个原始 Git blob。只接受固定原始源码或本仓库的两个精确适配文件，再复制到每轮私有目录；不复制旧 .env、日志、账号或数据库。随后验证 Ruby 版本和 frozen bundle，原生执行 db:create / db:migrate / db:seed，启动真实 Puma + AgentRunner。编译 assets 作为准备好的 SDK 输入使用；SDK 与 gem 的安装来源/完整性由 CI 的准备步骤管理，bundle check 仅验证锁定依赖可用，不是逐字节校验所有 gem。

原始锁文件 Ruby 元数据为 4.0.7，Gemfile 声明 Ruby >=3.4；本次保持两者不改，实际 3.4.11 满足 Gemfile。大小写不敏感排序、其他字符集和已有数据升级仍未验证。停止进程可能超时后强制结束，不能认证优雅停机。

## ntfy / Memos

两个应用使用固定源码构建的原生二进制。Memos 源码不改动；ntfy 显式增加 matrixone:// 后端和请求身份快照，补丁见 [matrixone-runtime.patch](fixtures/ntfy/matrixone-runtime.patch)。ntfy 的原生正常账号、deny-all ACL、共享 IP 限流和原生迁移保留；新 backend 不支持 populated upgrade / replicas / clustering / MatrixOne webpush。

可以传已有固定 SHA 的二进制：

```bash
python run_memos.py --binary /path/to/memos --out artifacts/memos-001
python run_ntfy.py --binary /path/to/ntfy --out artifacts/ntfy-001
```

SDK 构建入口要求 Go 1.27.1、固定完整 commit 的 pristine 源码、至少 4 GiB 入场余量；默认新建独立源码和缓存，不污染共享 Go cache。运行中若少于 2 GiB 或超过 30 分钟，会停止本次进程组并保留失败证据。

```bash
python build_go_sdk.py --app ntfy --source-tree /path/to/pristine-ntfy \
  --go /path/to/go1.27.1/bin/go --out runtime/ntfy-sdk-001
python run_ntfy.py --binary runtime/ntfy-sdk-001/ntfy \
  --build-manifest runtime/ntfy-sdk-001/build-manifest.json --out artifacts/ntfy-001

python build_go_sdk.py --app memos --source-tree /path/to/pristine-memos \
  --go /path/to/go1.27.1/bin/go --out runtime/memos-sdk-001
python run_memos.py --binary runtime/memos-sdk-001/memos \
  --build-manifest runtime/memos-sdk-001/build-manifest.json --out artifacts/memos-001
```

不同构建路径/选项产生的二进制 SHA 可能与历史缓存不同。驱动只接受历史固定 SHA，或与 SDK build-manifest 绑定、commit / Git blob 数 / Go 版本 / 补丁 hash 匹配的构建。build-manifest 是受信 CI 准备步骤生成的构建记录，不是供应链签名；应保护 SDK 和 manifest。第一轮在 workspace 的冷构建被真实磁盘入场检查阻止；随后转到容量足够的独立 /tmp 目录，ntfy 固定源码完整冷构建与 40 项新库业务实跑通过。Memos 的固定源码冷构建与 29 项新库复跑也已通过，详见 VALIDATION.md。

Go SDK 入口使用明确标记的 CLI 测试 HTML 占位资源及 ntfy 的 nofirebase/nopayments 构建选项，仅用于原生 API 回归，不提供完整 web UI 验收。

## mo-test CI 配置

原有 MO_TEST_* 连接密钥继续使用。新增仓库变量是 runner 文件路径：MO_HUGINN_RUNTIME_CONFIG、MO_NTFY_BINARY、MO_MEMOS_BINARY；若使用 SDK 新构建，再设置 MO_NTFY_BUILD_MANIFEST、MO_MEMOS_BUILD_MANIFEST。

默认 smoke 会执行所有十一个驱动；缺少 SDK 会失败，不能跳过后算通过。可显式选 `--app` / workflow app 输入只跑准备好的应用。load profile 当前仅迁移 Gotify、Blocky、Plik、Ergo 的负载入口；对其他七个选择 load 会明确拒绝，不伪造压力通过。新的 cold CI 与 GitHub Actions 仍待在容量足够的专用 runner 上执行。

## Baikal / FreshRSS

两个 PHP 应用使用固定 FrankenPHP/ PHP 8.5.11 SDK：MO_PHP_BINARY 指向与驱动 SHA 匹配的二进制。Baikal 使用官方 0.12.1 发行版，默认下载固定 ZIP 并逐文件核验；MO_BAIKAL_RELEASE_DIR 可指向已准备的目录，复制只包含固定发行版清单中的 1030 个文件，不带旧 config 或 INSTALL_DISABLED。原生网页安装创建 14 张表和原生账户；DAV 保留 Digest、ETag 和权限。

FreshRSS 的 MO_FRESHRSS_SOURCE_TREE 指向固定 4a810f16 的源码或仅带精确两文件补丁的 SDK。驱动校验 1294 个 Git blob/适配例外，复制到新私有目录，走原生网页安装全部步骤与原生账号/API 密码控制器；不通过 SQL 写用户或迁移记录。FrankenPHP 内嵌 CLI 的 getopt 差异原始失败保留。只有自建 RSS 服务的确切 127.0.0.1:端口加入原生 internal_host_allowlist；不放开其他内部地址。原生兼容 API 标题使用全角特殊字符，SQL 保留 HTML 编码原文。COMPRESS 的实测 framing 为长度前缀+raw DEFLATE，验证原文与长度，不认证与其他厂商压缩 BLOB 的格式互通。

MO_APP_RUNTIME_ROOT 可把私有运行副本放在另外的可写目录。当前测试使用 /tmp 的 tmpfs 与独立 6004 稳定版实例，旧 6001 实例和旧数据保留；tmpfs 容量同时消耗 cgroup 内存，不代表新增持久磁盘。CI 应配置容量足够的专用持久测试空间，并管理其测试库/私有运行目录生命周期。

Adminer 使用官方 6.1.2 all-language PHP 文件与固定摘要，默认下载；MO_ADMINER_RELEASE_FILE 可提供原始发布文件或精确适配 SHA。只有实际 MatrixOne 的解析后类型名转小写，完整类型/长度/枚举字面值不改。原生 PDO 路径、密码/cookie/CSRF 保留。它无内部迁移程序，所有业务 fixture DDL/DML 都通过原生 HTTP SQL 控制台/表单执行，Python 仅创建新库和读回。非法 CSRF 的原生 403 与错误提示是有效拒绝，不当成 MO 失败。HTML 表单解析依赖固定 wheel SHA 的 BeautifulSoup/soupsieve/typing_extensions；安装全部按 requirements.lock。

phpMyAdmin 5.2.3 从固定 SHA 的官方 all-languages tar.xz 重新解包 4314 文件，MO_PHPMYADMIN_RELEASE_ARCHIVE 可提供原始缓存包。驱动只接受完整官方 archive，不复制旧安装配置；三个源文件适配及原始/适配 SHA 随仓库发布。保留原生 cookie 密码认证、CSRF、真实查询、FK/回滚与 CSV；不启用或认证可选 configuration storage。SQL fixture 全部通过原生 HTTP 执行。

Kanboard v1.2.54 与 YOURLS 1.10.6 使用同一固定 PHP SDK；MO_KANBOARD_RELEASE_ARCHIVE / MO_YOURLS_RELEASE_ARCHIVE 提供原始 codeload tar.gz，或默认下载完整固定 SHA 并安全解包。只应用精确提交的两个/一个适配文件；原配置、账号、数据不复制。Kanboard 原生 139 迁移和新用户创建/私有项目、数据库 session 认证保留；初始 admin/admin 只在自建 loopback 实例 bootstrap 使用，随后经原生 API 删除。非法 CSRF 的原生 getValues 返回空请求，200 重新显示“标题必填”且零写入。YOURLS 配置账号按上游方式提供并由原生程序散列，所有管理账号共享全局权限，不认证跨账号隔离；跳转客户端不跟随外部目标。重复 URL 的原生 409 被准确断言，不当作成功新增。

Grafana 官方 OSS 13.2.3 包含原生网页资源，prepare_grafana_sdk.py --out /owned/new/sdk 流式下载并同时校验完整 archive SHA 与 13361 个文件的固定 SHA；未通过完整核验前不可执行。MO_GRAFANA_RELEASE_DIR 指向该 SDK；不提供时驱动自行准备新的 SDK。解压体积约1.38GB，准备额外保留2GiB。运行时目录独立，配置通过 GF 环境变量传递，密码无需 INI 插值；原生账号、cookie、853 迁移、统一 resource 存储和组织隔离保留。SQL relay 仅重写固定 NVARCHAR MODIFY DDL，不改认证/查询结果；TLS/compression 未覆盖。按原生配置 disable_legacy_table_rename=true 保留旧表，数据迁移仍执行。统一 alertmanager 初始化存在错误，该功能未认证；仪表板测试通过不能掩盖它。

Matomo 5.14.1 使用固定官方 tar.gz 与7个精确适配源文件。MO_MATOMO_RELEASE_ARCHIVE 可提供原包缓存，或默认下载验证；11888 个发行文件中的根级安装说明不执行，应用目录11887文件安全解包。原生网页安装先创建核心表，完成并启动插件后共34表。账号、bcrypt、站点权限和应用令牌均由原生安装/API生成；测试保留默认指纹识别，以不同语言的全新浏览器模拟三个独立访客，不关闭识别或伪造visitorId。原生一般API密码错误返回200+result:error，需要同时验证未新增令牌；无权限报告返回401。Live原生URL按存储的name和url_prefix重建后断言完整URL，原生登录cookie/令牌及访问记录重启保持。尚未认证归档聚合报表/rollup、插件与已有数据升级。


## Gogs 与 Apache Answer

Gogs 固定源码 dbbd717e923694c36f41b0360515b4374bbe6ee0、2646 个 Git blob 和128个精确 vendored XORM 适配文件。`MO_GOGS_BINARY` 提供历史固定 SHA 二进制；另一个构建必须提供 `MO_GOGS_BUILD_MANIFEST` 并匹配 source、Go、binary 和 adaptation-manifest hash。可用 `build_go_sdk.py --app gogs` 准备仅 API/Git 的 SDK；不产生 HTML 占位资源，两个指向 AGENTS 的源码符号链接验证 Git blob 后不复制。此次冷构建在4GiB入场阈值前被空间保护阻止，尚未执行冷编译。历史二进制原生 API/Git 的33项检查和统一入口复跑通过；其默认页面依赖未启动的 Vite，完整前端尚未验证。原生 fresh schema 初始化37表/版本22，不代表所有历史升级都已执行；并发 NextIssueIndex 竞争仍待单独处理。数据库密码以原生环境 ValueMapper 读取，不在 app.ini 插入明文；Git ASKPASS、配置和认证材料仅保存在私有 runtime。

Apache Answer 使用官方 v2.0.3 压缩包与固定 SHA 二进制，`MO_ANSWER_BINARY` 可提供原始发布缓存，否则默认下载并校验包和二进制摘要。源码 revision6744295，未修改 Go 程序。原生 CLI AUTO_INSTALL 调用自己的安装控制器创建完整新库、初始管理员和版本36，随后只通过官方配置修改监听地址为 loopback。普通账号、权限及问题/回答/标签全部通过原生 API。当前管理员权限来自 user_role_rel.role_id=2，不能用兼容旧字段 user.is_admin 判定。原生 SQLite 缓存及其令牌保持，权威业务数据连接 MatrixOne；完整 UI、SMTP、AI、MCP、插件及已有数据升级未认证。


## OpenCart

OpenCart 官方4.1.0.4 zip 固定 SHA 完整验证后仅安全解包 upload/ 发行文件，原始配置和数据不继承。`MO_OPENCART_RELEASE_ARCHIVE` 可提供原包缓存，否则默认下载；PHP仍使用固定FrankenPHP，`MO_PHP_BINARY`或统一binary-dir的frankenphp文件。五个精确PHP适配源文件分别验证原始/适配摘要：日期先过滤再按优先级选择价格的派生JOIN、SQL布尔字面量整数化、只跳过OPTIMIZE保留会话过期DELETE、PHP8.5 PDO常量同义兼容。按原生安装步骤准备空config、执行原生step_3.save创建159表及管理员，随后将本轮install目录移到私有目录，所有用户/token/商品/价格规则/购物车由原生安装或控制器生成，不手工插入。遵循上游部署设置将error_display=false，原始错误日志保留，不截取JSON尾部当作成功。原生文件session/cache保持，业务数据连接MO；上游原始fresh installer中的外键创建本就注释，不额外删约束。
