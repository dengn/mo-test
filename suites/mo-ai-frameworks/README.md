# AI 框架 MatrixOne 自动回归

22 个已适配项目、11 个隔离依赖组、33 个必跑测试。统一入口输出 JSON 和 JUnit；失败、超时、必跑用例跳过/缺失、端点未就绪或清理失败均返回非零。实际角色与固定包版本见 [projects.json](projects.json)，[本地执行证据](evidence/validation-report.json)来自 MatrixOne main `dd38098853ea197699ed3fac3e69dc53975ac061`。没有认证框架全部能力、真实模型推理、ANN、并发多写者或数据库容灾。

## 覆盖

| 隔离组 | 项目 | 必跑测试 |
|---|---|---:|
| core | LangChain、LlamaIndex、Haystack | 5 |
| storage | LangGraph、Agno、Memori | 3 |
| sessions | OpenAI Agents、PydanticAI、Google ADK | 5 |
| agents | AutoGen、Semantic Kernel | 3 |
| memory | Mem0；原生 Qdrant 本地对照 | 4 |
| tools | Smolagents、DSPy、LiteLLM | 3 |
| rag | LightRAG；原生文件对照 | 2 |
| javascript | LangChain.js、Vercel AI、Mastra | 3 |
| flow | CrewAI；原生 SQLite 对照 | 2 |
| scope | AgentScope Toolkit 与 typed AgentState | 1 |
| camel | CAMEL ChatAgent/ChatHistoryMemory；原生 JSON 对照 | 2 |

CrewAI 验证真实 Flow start/listen/persist、恢复后继续 11→22；AgentScope 验证真实工具与类型化状态，不是完整 Agent 模型循环；CAMEL 旧 context 进入下一次 ChatAgent 模型请求，使用 StubModel。其他模型依赖使用确定性替身。Mem0 SQLite history、LightRAG Graph/doc_status 保留原生存储。

[Top100 源码初筛目录](catalog/top100.csv)为 146 个策展候选按 2026-10-11 Stars 排序；25 项有实际接口/原生对照证据、75 项尚未集成实测。本正向门禁只纳入 22 个通过接入角色；MLflow、Langfuse、pgvector 原生阻断/对照单独记录，不算正向通过。本套件的计数与仓库已有大批次 case 分开。

## 执行

要求 Linux、Python 3.12、Node 24.19.0。各 Python 组独立 venv，完整依赖闭包固定版本；JS 通过 package-lock/npm ci 固定版本。配置目标端点的 MO_HOST、MO_PORT、MO_USER、MO_PASSWORD；账号须可创建/删除测试数据库。默认仅用于本地 fixture：127.0.0.1:6001、root/111。

```bash
cd suites/mo-ai-frameworks
python3.12 setup.py --group all
python3.12 verify.py
python3.12 -m unittest discover -s tests -p test_runner_contract.py -v
python3.12 run.py --group all --output results/my-run
```

只运行一个依赖组或项目：

```bash
python3.12 setup.py --group sessions
python3.12 run.py --group sessions --project google-adk --output results/adk-run
python3.12 run.py --group javascript --project langchainjs --output results/js-run
```

可用 --python 指定已安装该组依赖的解释器，或 --python-map 提供 group→解释器路径的 JSON。实际版本必须与 projects.json 完全一致。已存在的 --output 会被拒绝，防止覆盖历史结果。默认单组 300 秒超时，--timeout 可调整。

每轮只操作 `ai_reg_<12位run_id>_<12位随机数>` 数据库。先登记再建库，每例 finally 清理，运行器超时也执行独立清理；清理只接受当前 run_id 的完整名称。结果目录包含 environment.json、JUnit、日志、database registry 和汇总，不包含账号配置。运行时私钥、venv、node_modules、模型缓存均不提交。

## GitHub Actions

[ai-framework-regression.yml](../../.github/workflows/ai-framework-regression.yml)提供手工、可复用和 main 路径变更触发入口，11 组隔离执行，上传 JSON/JUnit。沿用仓库现有 `[self-hosted, Linux, X64]` runner，使用 MO_TEST_HOST、MO_TEST_PORT、MO_TEST_USER、MO_TEST_PASSWORD secrets 连接测试实例。runner 必须能访问该实例；工作流不启动/重置数据库。输入 group 支持 all 或上表组名。配置 secrets/runner 后即可持续运行；本地验证不冒充已经运行过 GitHub Actions。

## 已知问题与复现边界

[KNOWN_ISSUES.md](KNOWN_ISSUES.md)记录数据库问题、绕过与本批非数据库错误。Agno 保留版本固定的专用 engine 私有 dialect 绕过；OpenAI session 补 VARCHAR 长度、省显式子索引，保留 FK/CASCADE；JS 显式 utf8mb4；LangGraph 使用自定义同步 saver。CrewAI 凭据目录重定位只用于测试生成的隔离 key，保留 HOME。CAMEL 固定 MCP 1.28.1；恢复时先构造 ChatAgent 再通过公开 memory 属性挂载已有历史，避免构造器主动清空。

[evidence/validation/](evidence/validation/)保留每组最新完整通过的原始执行结果；此前运行器目录问题、Node 句柄超时与 CAMEL 模型替身失败保留在 evidence/*initial*。修正后仅重跑受影响组，不将重复尝试增加为逻辑测试数量。所有 33 个用例在本地已完成、清理成功；使用经过版本检查的既有隔离环境，尚未全组从空 venv 重装验证。源码与证据哈希见 artifact-manifest.json，verify.py 可离线检查。
