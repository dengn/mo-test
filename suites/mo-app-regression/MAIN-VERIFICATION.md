# 提交 MatrixOne issue 前验证 main

用户要求：每个新数据库问题在稳定版复现后，还必须在当时的 main 上验证是否存在。

1. 从 `matrixorigin/matrixone` 获取 main 的完整 40 位 commit，记录获取时间，独立检出并使用官方构建入口。运行实例的 `git_version()` 必须与该 commit 匹配。记录二进制 SHA、工具链及配置；旧工作区的二进制不能当作 main。
2. 稳定版与 main 使用独立测试库和相同复现 SQL、数据、断言。main 使用全新数据目录，保留原始稳定版应用数据。涉及 panic 的用例只在专用测试实例执行。
3. 核对执行结果值、关联、约束及触发后存活。没有报错但数据错误、变成其他错误或 fixture 初始化失败，都不能报告为已修复。
4. 新 issue 写明稳定版本、main 完整 commit、两边复现结果、完整 SQL、fixture 边界及证据。main 仍复现时提交；main 已修复时记录修复状态并保留回归。main 运行验证未完成时暂不提交，明确标记未验证。已有 issue 补充实测结果，不仅引用合并的 PR。

执行器可以拒绝连接到错误的 commit。连接密码通过环境配置，不写入命令参数或证据文件：

```bash
export MO_HOST=127.0.0.1 MO_PORT=6003
MAIN_SHA=<本次从上游获取并实际构建的完整40位commit>
.venv/bin/python run_sql.py --include-panic --allow-known \
  --expected-commit "$MAIN_SHA" --out artifacts/main-verification
```

`--allow-known` 仅用于观察已知问题。严格回归仍使用默认退出规则；已知失败不能算通过。JSON 记录运行时版本、运行时 commit、目标完整 commit、每个 fixture 的 hash 和逐条 SQL。短 `git_version()` 的前缀匹配还需与独立源码构建及二进制 hash 证据合用，不能独立证明任意外部服务器的来源。

本次已实测 main：`02a2823c2007d5e4fb4ada148e93743df337551a`。它包含针对 #29897 的修复 #29919；#29897 的 fixture 已核对通过。完整结果见 [本次证据](https://github.com/matrixorigin/matrixone-app-regression/tree/e3f59736522ec3128cc47b541d292fafc6dcfbd1/evidence/main-02a2823/README.md)。Piwigo #29961 在用户提出此要求之前已提交，本次确认 main 仍复现。

最新追加实测 main 为 `cd8d5abf9665a97d13e50b04840fb74b877fd339`，见 [最新运行证据](https://github.com/matrixorigin/matrixone-app-regression/tree/e3f59736522ec3128cc47b541d292fafc6dcfbd1/evidence/main-cd8d5ab/README.md)。历史 `02a2823` 证据保留当时结果，不能当最新状态。
