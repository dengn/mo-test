# Fivetran 官方 SDK 本地预检续跑（2026-10-12）

新增 **200 个独立场景全部通过**：25 类型 × 2 个归档来源角色 × 4 场景（重复 upsert、稀疏 update、delete 后 reinsert、checkpoint/resume）。官方 SDK 2.12.1、官方 Java tester 2.26.0908.001、DuckDB 本地目标，真实 SDK Operations、gRPC 和 tester 执行；未调用托管 Fivetran 服务。

源为先前经 SQL 全值核对的原生 Iceberg 快照，本轮重新验证 50 个源行集 SHA256。每组 32 行，包含 DECIMAL(65,30)、UINT64、BIT64、二进制、负 TIME、JSON NULL/SQL NULL、ENUM/SET、UUID 等。传输使用声明的规范化 STRING 信封；验证源值在该约定下保真，不等同于 SDK 目标原生类型映射，也没有实时 MO 读取/写入。

## 故障、恢复与演进过程

1. 新独立项目、空 DuckDB；每 10 个场景调用真实 `op.checkpoint`。在第 14 个场景发出第 8 次 upsert 后主动抛异常。官方 tester 非零退出，持久 `state.json` 为 `next_case=10`；保留异常日志与进程收据。这是刻意故障，不能作为产品 bug。
2. 新 Python/Java 进程从持久检查点 10 恢复，同一仓库最终达到 200。独立 DuckDB 全量读取验证全部 payload、rev、保留字段、有效主键、删除标记：6,400 物理行、6,000 有效行、400 删除标记、重复主键 0；200 个场景全通过。
3. 新进程的 schema callback 加 `schema_epoch STRING`，通过 SDK `op.update` 更新全部 6,000 有效行。再次全量核对 200 场景，旧字段和删除标记保留，新字段全部为 `v2`。
4. 新进程从已完成检查点再次执行，同一 schema 公告，官方 tester 的 upsert/update/delete/checkpoint 均为 0；再次全量核对 200 场景，含 SDK 元数据的仓库全值哈希与步骤 3 一致，持久状态相同。SDK 对此无数据空跑提示未调用 checkpoint 的建议，原始日志保留。

三次每次 200 的回读共 600 个检查，仍只计 **200 个独立场景**。幂等键 replay + 显式 checkpoint 的这一次故障恢复不能推导跨系统非幂等 exactly-once 或全部故障窗口认证；未做吞吐/长稳认证。

## 环境与范围

本轮开始时 `/workspace` 实测仍为 32 GiB 且可用 0，用户选定的至少 64 GiB 扩容未落实。已对明确归属本轮的 MO 测试进程 668920 发送 SIGTERM 并确认退出；旧数据库、目录、S3 桶、日志全部保留。使用独立 `/tmp` 临时文件系统做小规模 SDK 本地预检，Java 最大堆 512 MiB，现有官方 tester/JDK 只读复用，未启动 MO 重写入或降低磁盘保护阈值。

主重载计划仍为 **32,431/160,000**，剩余 **127,569**；本批归档来源、本地目标预检单独计数，不抵扣每工具 5,000 个实时重载用例。Fivetran 托管服务、原生 MO 目标、实时 MO 摄取和生产故障语义不在此预检覆盖内。

## 可检查材料

`evidence.zip` 保存 fixtures、完整操作/SDK日志、四个进程收据、三个全量回读 JSONL、源码、最终 `warehouse.db`/state 和本轮停止进程收据；`manifest.json` 给出每个成员和 ZIP 的 SHA256/大小，已复核 CRC 和全部成员哈希。SDK 测试源码可浏览于 `source/`。执行路径为历史路径，重跑需调整本地 SDK/Java 和目录路径，并在独立项目运行；不要覆盖现有项目数据。

核对顺序：`prepare_sdk.py` → `sdk_phase.py injected`（预期异常、检查 state=10）→ `sdk_phase.py resumed` → `audit_sdk.py resumed` → `sdk_phase.py evolve` → `audit_sdk.py evolved` → `sdk_phase.py noop` → `audit_sdk.py noop`。fixture 源目录需从前一个续跑检查点恢复，其原生目录位置也需调整。
