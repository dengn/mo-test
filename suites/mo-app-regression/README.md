# 开源应用自动化回归

直接连接真实 MatrixOne，启动固定版本的原生应用，执行业务、权限、逐值 SQL 核对和真实进程重启；每次新建随机测试库，输出 JSON 和 JUnit XML。此套件可独立执行，无需还原 mo-test 的历史分卷。

| 范围 | 当前覆盖 |
| --- | --- |
| 可独立运行的原生应用 | Gotify、Blocky、Plik、Ergo、Documize、Huginn、ntfy、Memos、Baikal、FreshRSS、Adminer、phpMyAdmin、Kanboard、YOURLS、Grafana、Matomo、Gogs、Apache Answer、OpenCart、Wakapi，共 20 个；版本/源码与原生二进制或 SDK 身份核验 |
| SQL 回归 | 20 个 fixture：4 个 panic、13 个其他已知问题、3 个正向对照；每个保留完整 SQL、错误签名、值及约束断言 |
| 历史应用运行 | 61 个真实尝试、58 个基本业务通过；其中 20 个独立驱动已迁移，其余 38 个基本通过项目待迁移，不计为自动化覆盖 |
| 候选目录 | 1000 项、939 项未运行；星数与许可证为记录时的快照 |
| CI | 手动 GitHub Actions + workflow_call，可接入现有流水线；本次本地运行结果见 [验证记录](VALIDATION.md) |

独立项目导入自 [matrixorigin/matrixone-app-regression](https://github.com/matrixorigin/matrixone-app-regression/tree/e3f59736522ec3128cc47b541d292fafc6dcfbd1)，身份与文件原始 hash 见 [upstream-import.json](upstream-import.json)。[inventory.json](inventory.json) 记录历史状态，[MIGRATION.csv](MIGRATION.csv) 按星数排列待迁移项目，[1000 项 CSV](catalog/projects-1000.csv) / [JSON](catalog/projects-1000.json) 保留候选和运行状态。此套件与原有 360,000 / 600,000 条历史 case 分开计数，不修改原有统计。

## 安装与运行

需要 Linux x86_64、Python 3.12、能够创建数据库的专用 MatrixOne 测试账号、至少 2 GiB 空闲磁盘。首次原生运行下载固定官方 release；依赖下载保留正常代理与 TLS 校验。

```bash
cd suites/mo-app-regression
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python verify.py
.venv/bin/python -m unittest discover -s tests -v
export MO_HOST=127.0.0.1 MO_PORT=6001 MO_USER=root
# MO_PASSWORD 从测试环境密钥提供，不写进仓库。
.venv/bin/python run.py --profile smoke --out artifacts/smoke-001
```

`smoke` 顺序执行 3 个正向 SQL 对照和全部 20 个原生应用。一个应用失败仍继续执行后面的驱动，最终返回失败；无报告、空报告或报告与退出码矛盾也会失败。输出目录必须是新目录，避免覆盖历史证据。

```bash
# 只运行一个应用；--app 可重复。SQL-only profile 不接受 --app。
.venv/bin/python run.py --profile native --app plik --out artifacts/plik-001
# 仅正向 SQL
.venv/bin/python run.py --profile controls --out artifacts/controls-001
# 严格门禁：已知问题存在时返回 1。
.venv/bin/python run.py --profile defects --out artifacts/defects-001
# 专用隔离实例上显式加入 panic 用例。
.venv/bin/python run.py --profile defects --include-panic --out artifacts/panic-001
# 观察模式允许精确匹配的 known_failure，但 JSON 中 passed 仍是 false。
.venv/bin/python run.py --profile observe --include-panic --out artifacts/observe-001
# 有限负载配置；不代表已达到极限容量。
.venv/bin/python run.py --profile load --out artifacts/load-001
# 仅列出命令，不连接数据库。
.venv/bin/python run.py --profile smoke --list
```

所有 profile 可传 `--expected-commit <完整40位SHA>`，连接版本不匹配时在创建测试库前阻止执行。Huginn 与源码构建应用的 SDK 配置见 [RUNTIME-SDK.md](RUNTIME-SDK.md)。缺少 SDK 会失败，不会静默跳过。

运行时短 SHA 匹配仍需与源码、官方构建和二进制 hash 证据合用；[提交新 issue 前的 main 验证要求](MAIN-VERIFICATION.md)继续适用。

可用 `--app-binary-dir /path/to/pinned-binaries` 提供名为 `gotify-linux-amd64`、`blocky`、`plikd`、`ergo`、`documize`、`ntfy-matrixone`、`memos` 的原生二进制，驱动逐一校验 SHA。离线环境需事先安装锁定的 Python wheel 并提供二进制；不会自动跳过 hash。Gotify 保留独立 `--archive` 入口。

## 回归和负载边界

| 应用 | 基本驱动 | load profile |
| --- | --- | --- |
| Gotify | 原生账号、应用/客户端、错误认证、16 条并发消息、分页、精确值和归属、重启 | 128 消息 / 4 workers |
| Blocky | 原生 DNS 和 GORM 迁移、64 查询、NXDOMAIN/拦截、逐条 SQL 日志、Unicode、重启后写入 | 1024 查询 / 32 workers |
| Plik | 11 个原生迁移、密码/cookie/CSRF、权限、16 文件的原字节/MD5/Unicode、SQL 关系、重启和删除 | 256 文件 / 16 workers |
| Ergo | 原生账号/频道、16 消息、成员权限、CHATHISTORY 分页、二进制 msgid、SQL 逐值、重启 | 1024 消息 / 8 writers，显式关闭原生 fakelag |
| Documize | 35 个原生迁移、登录/JWT、文档/章节/FTS、精确 SQL、真实重启，25 项 | 尚待迁移负载入口 |
| Huginn | 73 个原生迁移与 seed、Webhook→Formatter 后台处理、权限/CSRF、精确 SQL、真实重启，34 项 | 尚待迁移负载入口 |
| ntfy | 原生 CLI 账号/ACL、WebSocket/SSE、两用户并发身份、JSON/通知生命周期/附件、真实重启，40 项 | 尚待迁移负载入口 |
| Memos | 原生管理员注册/登录、私有笔记 CRUD、权限、并发精确值、真实重启，29 项 | 尚待迁移负载入口 |
| Baikal | 原生网页安装、CSRF 表单、两用户 Digest、CalDAV/CardDAV、ETag、精确 BLOB/归属、重启与删除，44 项 | 尚待迁移负载入口 |
| FreshRSS | 原生网页安装、原生账号/API 密码控制器、两用户 API、RSS 订阅、压缩正文/ID/归属、令牌拒绝、已读及重启，30 项 | 尚待迁移负载入口 |
| Matomo | 原生网页安装/34 表、账号/令牌/站点权限、访问-动作-URL 精确关系、Live 报告与重启，31 项 | 尚待迁移负载入口 |
| Grafana | 官方 OSS/853 原生迁移、普通用户/组织隔离、仪表板精确 JSON、CSRF、SQL 与真实重启，27 项 | 尚待迁移负载入口 |
| Kanboard | 原生 139 迁移、普通用户私有看板/并发任务/评论、权限/CSRF、SQL 与重启，34 项 | 尚待迁移负载入口 |
| YOURLS | 原生安装/认证/nonce、短链 Unicode/重复拒绝/编辑、跳转/点击日志、SQL 与重启删除，28 项 | 尚待迁移负载入口 |
| phpMyAdmin | 原生密码/cookie/CSRF、SQL 控制台/类型/FK/回滚、精确 CSV 与重启，22 项 | 尚待迁移负载入口 |
| Gogs | 原生初始化 37 表、密码/令牌/私有仓库、真实 Git HTTP clone/push、issue/评论、SQL/权限/重启，33 项 | 尚待迁移负载入口 |
| Apache Answer | 官方原生安装/版本36、账号/角色、问题/回答/标签/Markdown、SQL/权限/重启，27 项 | 尚待迁移负载入口 |
| OpenCart | 原生网页安装/159表、密码/cookie/token、Unicode商品、日期过滤折扣/特价、购物车精确金额、SQL关系/权限/重启，35项 | 尚待迁移负载入口 |
| Wakapi | 原生14表/FK、三账号/密码/API key、两用户16条心跳全部精确落库、去重/权限/实际重启，40项；重启等待界限180秒 | 尚待迁移负载入口 |
| Adminer | 原生 PDO/密码/cookie/CSRF、SQL/表单/类型/FK/回滚、CSV 精确值与重启，20 项 | 尚待迁移负载入口 |

Ergo 仅把原生 MySQL 聊天历史后端接到 MO，账号/频道仍使用原生 BuntDB。Blocky DNS ACK 还必须与持久化日志核对；缺失不会算通过。已有高负载失败和恢复仍保留在独立项目证据里，后续成功不会覆盖早期失败。完整 UI、插件、已有数据升级和生产长期稳定性不属于本轮覆盖。

入口在执行前检查剩余磁盘，默认要求 2048 MiB，`--min-free-mib` 最低 128；自定义值写入报告。原生低阈值验证必须提供已有的同 SHA 二进制；Blocky/Plik 限制为基本工作量，load profile 至少要求 2048 MiB。该检查是入场检查，运行中资源上限由专用 runner / 容器控制；不要把固定的有限负载当作自动饱和测试。本次磁盘不足，使用已有二进制/SDK及显式较低入场阈值验证基本驱动，没有执行 load profile。

## CI 接入

配置仓库密钥 `MO_TEST_HOST`、`MO_TEST_PORT`、`MO_TEST_USER`、`MO_TEST_PASSWORD`，使用能访问专用测试实例的 `[self-hosted, Linux, X64]` runner。工作流 [.github/workflows/app-regression.yml](../../.github/workflows/app-regression.yml) 支持手动选择 profile / app / panic / commit，也可被现有 CI 调用：

```yaml
jobs:
  native-apps:
    uses: dengn/mo-test/.github/workflows/app-regression.yml@<reviewed-commit>
    with:
      profile: smoke
      expected_commit: <actual-matrixone-build-full-sha>
    secrets: inherit
```

`defects` 始终是严格门禁，已知失败不会被忽略；`observe` 用于诊断，不能替代发布门禁。panic 默认关闭，仅允许在 defects / observe 下显式开启。工作流只上传 `artifacts/` 结构化结果，私有 `runtime/` 配置、应用日志和凭据不上传。

每个驱动仅创建随机 `mo_reg_*` 新库，不写已有应用库、不自动 DROP。测试库保留便于诊断；生命周期管理只处理本套件确实创建的测试库。原生进程由本轮驱动停止，私有目录 0700、日志及配置 0600。不得上传 runtime、环境变量转储或任意未经筛选的应用日志。

## 继续迁移项目

已完成适配的项目可以按同一接口继续接入。每个新驱动需要固定源码/release 身份、可复现依赖与适配、原生建库/迁移、真实业务和拒绝路径、逐值数据/关联/权限断言、真实重启及失败退出码，且与旧工作目录和账号解耦。通过独立运行后再把 inventory 的 pending 改为 implemented，并更新入口、工作流和清单 hash。

Huginn 与 Documize 适配源代码保存在 [adapters/](adapters/README.md)，现已成为独立驱动；ntfy 的 MatrixOne 源码补丁见 [fixtures/ntfy/](fixtures/ntfy/)。相关原始 SQL 回归仍保留在 `cases/`。其他应用仍按 MIGRATION.csv 的原状态跟踪；重启、压力或迁移失败不能被“基本业务通过”掩盖。

`MO_APP_RUNTIME_ROOT` 可以指定容量足够的独立私有运行目录；默认在套件 runtime/ 下。磁盘入场阈值检查该目录所在文件系统。若选用 /tmp 等 tmpfs，它会占用内存且具有临时性；原始证据仍输出到 artifacts/ 后归档。新迁移 PHP 驱动另需 MO_PHP_BINARY 以及对应固定源码/发行版 SDK，见 RUNTIME-SDK.md。
