# 已知问题与绕过

SQL/驱动 bug 在 main dd38098853 编译实例与 MySQL 对照确认。以下 issue 的开放状态核对时间为 2026-10-14，非实时状态。

| 触发 | 归因与跟踪 | 回归接入 |
|---|---|---|
| JSON_TABLE VARCHAR CHARACTER SET utf8mb4 解析失败 | MatrixOne [#29914](https://github.com/matrixorigin/matrixone/issues/29914) | LangGraph 自定义同步 saver |
| indexed CASCADE 空匹配删除 executor panic | MatrixOne [#29954](https://github.com/matrixorigin/matrixone/issues/29954)；90-case 矩阵含12次panic | OpenAI Agents 新表补 VARCHAR 长度并省显式子索引，保留FK/CASCADE；不是数据库修复 |
| mysql2 默认 collation 224 握手失败 | MatrixOne [#30014](https://github.com/matrixorigin/matrixone/issues/30014) | 显式 charset=utf8mb4；其他collation语义需另验 |
| SQLAlchemy VALUES AS new upsert | 已有 [#28160](https://github.com/matrixorigin/matrixone/issues/28160#issuecomment-6110343645)补 Agno 证据 | 专用 engine legacy VALUES upsert，私有属性需固定版本 |
| MLflow ALTER ADD CHECK 迁移失败 | 已有 [#25387](https://github.com/matrixorigin/matrixone/issues/25387#issuecomment-6110343452)补证据 | 不纳入正向通过门禁，未静默删约束 |
| Langfuse PG驱动 / pgvector扩展与MO不兼容 | 原生架构/方言边界 | 单列原生阻断/对照，不算通过 |
| langchain-matrixone 忽略 metadata filter | 适配包错误 | 本地先过滤再top-k；复杂过滤未实现 |
| CrewAI 写固定用户凭据目录受限 | SDK/执行环境问题，未访问DB | 仅测试重定位 fixture key，不修改HOME |
| CAMEL 最新MCP2.x无 mcp.server.FastMCP | 上游依赖接口变化，未访问DB | 固定mcp1.28.1；pip check通过 |
| CaptureStub._run 参数签名漏位置参数 | 测试替身错误，三端同样失败 | 修正后JsonStorage/MO/MySQL三端通过；保留初始结果 |
| pytest tmp_path 父目录不存在 | 运行器目录问题 | 先建runtime；Mem0/LightRAG重跑通过 |
| Node用例结束但SDK句柄未退出 | 测试运行器清理问题 | Node原生 --test-force-exit，失败断言仍返回非零 |

本轮新增 CrewAI、AgentScope、CAMEL 没有确认新的 MatrixOne 核心 bug。已知 issue 的详细原始探针保留在独立 AI 适配报告，本套件保存通过门禁的版本、源码链接、JUnit和后端结果。

DeepAgents 首次按旧版行列表校验新版 StateBackend 字符串 content，六条原生/MO/MySQL失败均属于测试接口假设，已修正重跑；LangExtract 首次 ResolverParsingError 导入模块不正确，未访问DB。原始失败保留在 evidence/deepagents-initial-state-shape.json 和 evidence/langextract-initial-import.log。新四项没有确认新增MO核心bug；2026-10-14五个已报问题均仍open，快照见 evidence/issue-status-2026-10-14.json。
