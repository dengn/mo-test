# MatrixOne 压力、边界与混沌测试

此仓库保存本次测试的 **600,000 条主用例**、参数化生成器、执行器、固定来源清单、运行记录和最小复现。原先 500,000 条已执行结束；随后两批各 50,000 条执行期间，仓库保存明确标为 running 的结果快照，结束后更新。实际完成数量以 [manifest.json](manifest.json) 为准，不把校准、复核或额外压力操作加进主用例数量。

| 用例 ID | 测试包 | 主用例数 | 内容 |
| --- | --- | ---: | --- |
| C | [mo-cases-50000](suites/mo-cases-50000) | 50,000 | 手册、MySQL 公开用例、MatrixOrigin 仓库 |
| H | [mo-chaos-50000](suites/mo-chaos-50000) | 50,000 | 复杂 SQL、混合负载、取消、断连、5 次 SIGKILL |
| X | [mo-crossdb-100000](suites/mo-crossdb-100000) | 100,000 | Doris、StarRocks、TiDB、ClickHouse、TDengine、Milvus 场景 |
| E | [mo-etl-100000](suites/mo-etl-100000) | 100,000 | Snowflake、Fivetran、dbt 场景，真实文件导入/导出 |
| G | [mo-gap-200000](suites/mo-gap-200000) | 200,000 | 约束、窗口、CTE、混合类型、高维向量、并发边界 |
| K | [mo-corners-50000](suites/mo-corners-50000) | 50,000 | TLS、权限、SQL/Python UDF、存储过程、task、Iceberg |
| M | [mo-enterprise-50000](suites/mo-enterprise-50000) | 50,000 | 用户/角色、多租户、事务、发布订阅、Git4Data |

最早三轮独立压力测试的脚本、数据和报告在 suites/mo-stress、suites/mo-vector-fulltext、suites/mo-extreme-round2，包含向量/全文大数据集、256 并发、spill 与故障恢复；不计入上述 60 万条。

## 查看与完整性校验

用例和结果以每 5,000 条一片的 jsonl.gz 保存；每个 JSON 对象保留稳定 ID、SQL、参数、预期与来源。manifest.json 记录逐片 SHA-256、条数、整包还原后的 SHA-256、结果状态与完成数量。全部物化用例均上传，不仅保存生成器。

~~~bash
python3 tools/materialize.py --verify-only --output /tmp/mo-test-verify
python3 tools/materialize.py --output /tmp/mo-test-restored
~~~

第二个命令还原原来的 cases.jsonl / results.jsonl、CSV/Parquet 等文件输入输出、来源缓存及 NumPy 数据；遇到已有目标目录会拒绝覆盖。使用 Python 3.12 或更新版本。

## 执行

测试固定 MatrixOne main 提交 **2726fb419b3afa1db2686ae1b2aaca563d1ae214**；主测试使用 MySQL 8.0.46 对照。原始前 50 万条使用 PyMySQL 1.2.3；新增功能批次环境升级到 PyMySQL 2.2.8。版本不同可能改变类型转换或默认 TLS 行为，应记录版本后再比较。

原始脚本与部分 SQL 文件路径使用 /workspace/mo-*。在独立测试机器或容器中还原到 /workspace，安装依赖并按 suites/mo-stress/config 配置本地 MO 服务。默认 SQL 端口 6001；MySQL 对照端口 63306。数据及密码 111 都是本地合成测试配置，TLS 证书需要重新生成；仓库不包含私钥、数据库运行目录或真实环境凭据。

前五包完整重放入口是：

~~~bash
/workspace/mo-stability-500000/run_all.sh
~~~

此脚本建立新的独立数据库，包含 **5 次主动 SIGKILL**，针对配置所指向的本地 mo-service 测试进程。原始结果和校准错误同时保留；恢复写入账本用于核对已经确认的事务。恢复测试应运行在独立测试服务上。

新增两包使用 mo-corners-50000/setup.py 准备本地用户、角色、过程、UDF 与 task，再执行各包的 runner.py。执行前需要：

- 使用同一 CA 签发服务端及有效、无效、过期客户端证书，放到 mo-corners-50000/certs；前端 TLS 使用 enableTls 配置。
- 独立启动仓库内 pyserver/server.py，CN 的 Python UDF client 指向 127.0.0.1:50051。
- 准备真实 Iceberg REST 目录、对象存储和 ice_events 外部表。此次本地环境为 Nessie 0.107.3 + Moto S3 测试服务 + 真实 Iceberg v2/Avro/Parquet 文件。
- 当前 Nessie /credentials 接口返回 500；catalog-bridge.py 将官方 LoadTable 已返回的真实临时凭据转换为该接口格式，其余请求转发到 Nessie。**有此适配器的测试不能证明未修改 Nessie 接口与 MO 完全兼容**。原始失败及适配后的 E2E 证据分开保存。

执行器保留拒绝原因；TLS 超时不当成证书校验成功，权限测试不将任意语法错误当成正确拒绝。新增用例状态仍需根据原始记录复核。

## 已完成报告与限制

[原先 500,000 条报告](suites/mo-stability-500000/REPORT.md)说明原始/复核分类、已确认索引元数据异常、兼容性候选及运行限制。problem-groups.json 与最小复现支持按根因归类，失败条数不等于 bug 数量。

跨库和 ETL 批次验证的是公开场景在 MO 上的实现；未部署六种对照数据库、Snowflake/Fivetran SaaS 或实际 dbt adapter。大多数精确结果用例基于小数据固定预期，大数据压力脚本单列；本次 4 CPU / 32 GiB、单进程 LOG/TN/CN 的结果不能直接证明分布式或 TB 级生产行为。用例实例数也不等于独立功能数。

来源及固定版本记录在每个包的 source-manifest.json。保留了导入代码、公开测试和文档中的原始版权声明；来源项目的许可证仍适用于其对应文件。


## Final execution update

All 600,000 main cases have completed. See [the additional 100,000-case final record](suites/mo-stability-500000/EXTRA-100000-FINAL.md), the retained raw statuses, and [submitted issues](ISSUES.md). Rechecks do not increase the main count.

## Additional column and GIS probes

These follow-up probes are separate from the completed 600,000 main cases.

- [Physical column boundary](suites/mo-column-boundary/README.md): 1,000 and 10,000 columns passed; 65,530 passed full-row read/write and forced-flush verification; 65,531/65,532 produced wrong tail reads; 65,533 and 100,000 caused a fatal server panic, reported as [#30011](https://github.com/matrixorigin/matrixone/issues/30011). The million-column probe was discontinued at the user's request. Service recovery and original errors are retained.
- [Native GIS verification](suites/mo-gis-check/README.md): main and v4.2.5 source contain native GIS types; 106 runtime checks cover 18 type/alias forms, WKB/GeoJSON, SRID, math and spatial index maintenance. All checks matched expectations, including nine explicit unsupported/invalid-input rejections. Tested binary and inspected main revisions are recorded separately.

- [GIS/PostGIS functional and application comparison](suites/mo-gis-postgis/REPORT.md): current main f1fc3f9; 13925 differential cases, 106 type checks, 1582 official BVT checks and 416 Go test/subtest events. Includes OpenLayers, GeoDjango, indexed workflows and SIGKILL recovery. Three confirmed MO defect groups and one reference-side area anomaly are documented with drafts; no new issues have been posted. [GIS introduction history](suites/mo-gis-postgis/HISTORY.md) traces the first main merge to 2026-04-15. Initial setup misconfiguration left the old 6001 cluster unable to replay WAL; original data is preserved and formal GIS tests use an independent healthy 6011 cluster.

- [Latest-main GIS verification and application suitability](suites/mo-gis-main-recheck/README.md): rebuilt main `0a4db0e6`, 81 three-engine constant queries plus 8 stored/admission records; all three confirmed defects persist and were reported in English as #30032/#30033/#30034. New application checks passed; SRID4326 spatial-index pushdown is deliberately disabled while the planar index path works. These follow-ups do not increase the 600000 main-case total.
