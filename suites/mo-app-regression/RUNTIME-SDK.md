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
