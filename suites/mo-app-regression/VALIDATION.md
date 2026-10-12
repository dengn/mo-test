# mo-test 接入实跑验证

本轮在隔离环境实际运行 MatrixOne 官方稳定版 v4.2.5，完整构建 SHA `1a44f3db3056e32975fde86ca0ab69a094996a3f`，运行时 git_version `1a44f3d`。结果记录使用 UTC 时间；每个业务驱动使用全新的随机库。

| 验证 | 实际结果 |
| --- | --- |
| Python 合同测试 | 14 项通过，覆盖错误签名、失败继续执行、缺失报告、观察标签、健康失败、panic opt-in、未迁移应用、commit 和低磁盘负载拒绝 |
| Gotify 原生业务 | 12 项通过：16 消息 / 4 workers，真实 API、SQL、权限和重启 |
| Blocky 原生 DNS | 10 项通过：64 查询 / 4 workers，精确持久化日志和真实重启 |
| Plik 原生文件服务 | 17 项通过：16 文件 / 4 workers，原生认证/CSRF、字节/MD5、权限、SQL、重启和删除 |
| Ergo 原生聊天历史 | 13 项通过：16 消息 / 2 writers，原生 fakelag 保留，IRC/SQL/权限/重启 |
| smoke SQL 对照 | 3 项通过：Unicode/JSON、事务回滚、生成列 UPPER 索引 |
| 全部 20 SQL fixture（观察） | 17 known_failure、3 passed，所有触发后健康检查通过；观察返回 0，但 suite passed 为 false |
| 严格缺陷门禁（默认不含 panic） | 13 known_failure、3 passed，正确返回 1 |
| 错误完整 commit | 在创建测试库前阻止，返回 2，jobs 为空 |
| 默认磁盘阈值 | 2 GiB 入场要求因本地约 330 MiB 余量被拒绝，返回 2，jobs 为空 |
| 凭据检查 | 对当前检出的 115 个公共文件检查 113 个历史私有值，无命中；runtime/artifacts 未提交 |
| Workflow | YAML 与接入字段校验通过；没有在 GitHub Actions 执行，没有配置或改写仓库密钥 |

证据目录：[evidence/integration/](evidence/integration/)。每个应用和 SQL 执行均保留 JSON / JUnit。主入口子任务级 JUnit 与子目录断言级 JUnit 是不同粒度，不能相加当作独立业务检查数量。

第一轮 Gotify / Ergo / 3 个 SQL 对照通过，Blocky 和 Plik 因各自旧的 2 GiB 保护被阻止，最终返回 1。该轮原始失败保存为 `integration-smoke`。统一入口与两驱动的入场阈值、直接使用同 SHA 本地二进制后，独立第二轮 `integration-smoke-round2` 全部通过；没有覆盖第一次失败。

本次有限基本验证显式使用 `--min-free-mib 128`，二进制逐一校验 SHA，直接执行本地文件，不复制或重新下载。默认 CI 仍要求 2048 MiB；低阈值原生验证要求已有二进制，Blocky/Plik 限定基本工作量，load profile 仍要求至少 2048 MiB。本次没有执行 load profile，也没有声称达到饱和容量。

17 个已知失败中包含 4 个既有恢复型 panic；这不代表本轮新发现 4 个独立 panic，也不代表服务进程退出。已有 main 的状态与稳定版不同，本轮不对最新 main 宣称缺陷仍存在，不提交新 issue。新增 issue 仍须按 MAIN-VERIFICATION.md 实际验证当时 main。

历史 58 个基本业务通过中的其余 54 个尚未做成独立驱动；61 个历史尝试中有 57 个驱动待迁移。1000 项总任务仍有 939 项未运行。此 PR 是已具备独立驱动的首批接入。
