from runtime import *
x=json.loads((B/'certification-summary.json').read_text());s=x['soak'];res=x['resource_observations'];through=x['throughput_60s']['direct'];stairs=x['staircase']['stages'];parallel=json.loads((B/'exactly-once-parallel-result.json').read_text())
assert s['status']=='passed_observed_30min_scope' and s['load_end_elapsed_s']>=1800 and not s['source_errors']
assert all(v['all_fields_equal'] for v in s['final'].values())
assert all(c['status']=='passed' for c in x['typed_fidelity']['cases'])
lines=['\n\n## 第三轮：2026-10-11 吞吐、30 分钟持续负载与 exactly-once 故障认证',
'### 环境与判定范围',
'MatrixOne 本地源码构建 `'+REF+'`，单节点 + MinIO；MySQL 8.4.11、Kafka 3.9.1/KRaft、Debezium MySQL/JDBC 3.1.2.Final、NiFi 2.4.0、Java 21、kafka-python 2.2.15。所有服务同机共享 4 CPU quota / 16 GiB；不是最新 main / 独立硬件容量 / 多节点认证。本轮 Airbyte 未参与吞吐、长稳或 EOS 测试。',
'### 吞吐：持续样本与端到端阶梯',
'直连 Python MySQL text protocol 对小规模重复 key 执行 upsert，**行操作数而非新增唯一行数**；每档 60 秒，4 个客户端，并发于下述持续 CDC 负载。p99 为一批事务的提交延迟。',
'| 每批行数 | 实际运行秒 | 成功行操作 | 行操作/秒 | 批事务 p99 ms | 错误 |',
'|---:|---:|---:|---:|---:|---:|']
for t in through:lines.append(f"| {t['batch_rows']} | {t['duration_s']:.3f} | {t['acknowledged_row_operations']} | {t['ack_row_ops_per_s']:.2f} | {t['transaction_ms_p99']:.2f} | {len(t['errors'])} |")
lines += ['早先 8 秒短样本最高约 10594 行操作/秒，不能用作生产容量承诺；60 秒单行压测时 CDC 部分 30 秒窗口 p99 升至约 6–9 秒，说明混合负载下需要同时约束吞吐与尾延迟。',
'端到端路径：MySQL → Debezium source → Kafka → Debezium JDBC sink → MO，以及 MySQL 事务 SQL outbox → NiFi QueryDatabaseTableRecord → SplitRecord → EvaluateJsonPath → ReplaceText → PutSQL → MO。每档额外输入持续 60 秒；同时有 Kafka 10/s、NiFi 5/s 背景负载。按 250ms 轮询记录目标首次可见，含源提交/队列/批处理，不是数据库内生延迟。',
'| 路径 | 额外输入行/秒 | 发送/最终可见 | 端到端 p99 ms | 含排空耗时秒 |',
'|---|---:|---:|---:|---:|']
for t in stairs:lines.append(f"| {t['route']} | {t['requested_input_rows_per_s']} | {t['submitted']}/{t['target_visible']} | {t['latency_ms_p99']:.2f} | {t['elapsed_including_drain_s']:.3f} |")
lines += ['5 个阶梯加 1000 行 Kafka / 500 行 NiFi 突发，共 27000 行独立样本，源端与目标逐字段完全一致；不是仅按 COUNT 判定。覆盖 unsigned64 最大值、signed64 最大值（NiFi）、DECIMAL(38,18)、00FF80 二进制、中文/emoji、微秒 DATETIME、JSON 内 9007199254740993 大整数及产生时间戳。源/目标规范化 SHA256 一致。',
'### 实际 30 分钟持续运行与故障恢复',
f"开始 UTC `{s['started_UTC']}`；持续负载实际 `{s['load_end_elapsed_s']:.3f}` 秒，再排空 `{s['drain_s']:.3f}` 秒；判定 `{s['status']}`。",
'Kafka 每秒插入 10 行、NiFi 每秒 5 行；每分钟每条路径做一次删除和一次更新。更新 name/微秒 ts，删除源端已产生行；同一批复杂数据类型。生产者在服务故障期间继续写 MySQL。',
'| 路径 | 插入事件 | 每路主动删除 | 最终源/目标行 | 全字段相等 | 目标总数/不同 PK | 含故障 p99 / 最大首次可见延迟 ms |',
'|---|---:|---:|---:|---|---|---|']
for route in ['kafka','nifi']:
 f=s['final'][route];l=s['latency'][route];lines.append(f"| {route} | {s['generated'][route]} | {f['intentional_source_deletes']} | {f['source_rows']}/{f['target_rows']} | {f['all_fields_equal']} | {f['pk_count'][0][0]}/{f['pk_count'][0][1]} | {l['ms_p99']:.2f} / {l['ms_max']:.2f} |")
lines += ['计时终点有一次已等待中的生产 tick 完成，因此实际 Kafka/NiFi 插入事件为 18010/9005；每路 30 次删除。原始 soak-result 的 generated 字段仍为最后一次采样拷贝的 18000/9000；最终 soak-progress=18010/9005，与最终源端行数+删除数、可见性样本数一致。保留原始回执，并在汇总中明确调和这个采集快照时序差异，以实际事件计数为准。']
lines += [f"源端错误 `{len(s['source_errors'])}`；最终复杂字段全部比较，含全部更新与删除传播。可见性监控每约 0.5 秒轮询，资源/积压每 30 秒采样；服务停机的查询报错另存日志，不伪装为源端写入错误。最终 PK 唯一只证明快照无重复，**不认证非幂等业务效果 exactly-once**。",'故障全部为真实 SIGKILL，3 秒后启动同配置/同持久状态：']
for f in s['faults']:lines.append(f"- `{f['name']}`：开始后 {f['elapsed_s']:.3f} 秒，UTC `{f['UTC']}`。")
for r in x['recovery_observations']:
 bound=r['sampled_recovery_upper_bound_s'];lines.append(f"- {r['fault']} 故障 / {r['route']} 路径：{bound:.2f} 秒内在 30 秒采样中回到不超过 2 秒插入量的小积压；这是采样上界，不是精确 RTO。" if bound is not None else f"- {r['fault']} / {r['route']} 未观察到回归正常积压。")
lines += ['Kafka worker、MO、NiFi 的重启均由测试控制器执行，不等于进程自身可用性恢复。MO 故障后 JDBC sink task FAILED，控制器显式重启次数 '+str(len(s['controlled_task_restarts']))+'；必须标为受控恢复。NiFi 同一 flow/state/content repository 重启后追平，无需重建 flow；故障前后之前保留的 1 条非法数据仍在停止的 reject 队列，正常活动队列已排空。',
f"4 CPU quota 利用率采样均值/最高 {res['cpu_quota_utilization_mean_percent']:.2f}%/{res['cpu_quota_utilization_max_percent']:.2f}%；磁盘空闲初/末 {res['free_disk_MB_first']:.1f}/{res['free_disk_MB_last']:.1f} MiB；RSS 峰值 MiB `{json.dumps(res['rss_MB_peak'])}`。记录增长、缓存与 MO 重启影响 RSS，30 分钟不足以证明不存在泄漏。650 MiB 磁盘 guard 未触发。",
'### exactly-once：有明确失败，也有范围受限的正向证据',
'- **原生 Kafka JDBC append sink：失败。** DB 可见 100 行、topic end=100、committed offset=NULL 时强杀 sink worker；重启后 MO 200 行/100 IDs，topic end 仍为 100。真实提交后、offset 提交前窗口；没有新增源事件或人工 rewind。',
'- **原生 NiFi 非幂等 PutSQL：失败。** 仅生成 1 FlowFile，COMMIT 成功 OK 被代理丢弃，数据库计数先为 1；FlowSession 重试后为 2，queue=0。不是 MO ACID 缺陷，而是数据库 commit 与 FlowFile session commit 没有原子协议。',
'- **自建事务账本/checkpoint 适配器：指定故障窗口通过。** event_id 去重账本、业务累加、MO checkpoint 同一事务；之后提交 Kafka offset。commit 前消费者 SIGKILL、commit 后 Kafka ACK 前 SIGKILL，100 个事件最终账本/累计=100；第 105 个事件未提交时 MO SIGKILL，恢复后已提交状态仍为 104，继续到 120 后账本/累计/源端均为 120。',
f"- **额外并发去重控制：{parallel['status']}。** 4 分区/4 显式分配 consumer，各自打乱相同 200 个稳定 ID，合计 800 投递；最终 ledger/distinct/sum=200/200/200，业务累计=200，各分区 MO checkpoint=199。一次 1062 并发唯一键冲突回滚后重试，最终无错误。耗时 {parallel['duration_s']:.3f} 秒。此组没有 rebalance/HA 或故障注入，不能与单消费者故障组拼接成完整并发 EOS 认证。",
'- **原生 Kafka producer 事务隔离：通过。** 10 条 open / aborted 事务消息不可见，LAST_KAFKA_MESSAGE_ID=NULL；另 10 条 committed 消息全部可见，消息 offset 为 11..20，last ID=20（abort 控制记录占用了 offset）。这只是 read_committed source 视图。',
'- **原生 SQL broker offset：语句级边界。** 3 次独立 COMMIT、ROLLBACK、后续 1062 再 COMMIT、disconnect，共 12 组。成功 INSERT 后 ROLLBACK/disconnect 得到目标 0 行但 broker offset=1；后续失败再 COMMIT 得到数据 1 行/lastID=0/offset=1，当前版本未复现旧 #27587。源码明确 broker progress 不是 SQL transaction state，应另存 MO checkpoint。',
'### 配置、误差与排除项',
'- NiFi SplitRecord/EvaluateJsonPath/ReplaceText/PutSQL schedulingPeriod=0sec，PutSQL batch=100、rollback-on-failure=true，QueryDatabaseTableRecord=1sec。一般不可用故障时回滚/保留待重试数据；非法记录在单独停止队列保留。',
'- 正式 30 分钟前默认内容归档遇到宿主磁盘压力，NiFi 出现 archive constraints/30 秒停顿。保留那段原始证据，停服务将 `nifi.content.repository.archive.enabled=false` 后排空，再用全新 ID 范围启动完整 1800 秒。没有拼接早期约 90 秒充作 30 分钟。',
'- 正常 Connect worker offset.flush.interval.ms=1000、scheduled.rebalance.max.delay.ms=1000；专用 EOS 反例 worker flush=60000、source EOS enabled。MySQL source required-EOS preflight 未实现不能认证 source，但不据此断言所有 source EOS 不可能。',
'- 初版 Kafka Python OffsetAndMetadata 参数缺失已修正后重跑；初版 NiFi status URL 404 是采集错误，读取同一次完成的 processor entity status，没有再注入。',
'- JSON 投影初探、错误 start_id=0 的 autocommit=false 空读，以及与 MO SIGKILL 重叠的首组 full-field COMMIT timeout，均未计入有效事务语义结果。纠正 read start 后使用新的 topic/group 重跑；投影缺陷本身真实独立复现并立新单。',
'### 新增与关联 issue',
'- #29856：合法 Kafka JSON 的严格模式投影报 20301、非严格元数据投影静默 NULL；3 重复 × 2 格式 × 2 SQL 模式，72 SELECT+6 INSERT SELECT 控制。关联已关闭 #26264 的不同文件投影缺陷。',
'- #29857：Kafka Connect / NiFi 原子事件账本与 checkpoint sink 模板/适配器请求，包含上述两个原生失败反例和正向事务实现的详细过程。',
'- #27587：保留旧版本问题，已补当前 SHA 的三次事务进度复测及语句级契约；未擅自关闭。',
'- #27746：Flink 生态认证相关，未因本轮通过而宣称 Flink EOS 已认证。',
'下一阶段优先：修复 #29856；交付 #29857 并自动化故障矩阵；落实自动 task 恢复/拒绝队列策略与 SLO；在独立容量足够的环境进行 24–72 小时、大数据集、多节点与 consumer rebalance/HA 测试。当前结论是**30 分钟受控恢复与快照保真通过，原生非幂等端到端 EOS 明确失败**。']
content=lines[0]
for prev,line in zip(lines,lines[1:]):content+=('\n' if prev.startswith('|') and line.startswith('|') else '\n\n')+line
(B/'issue-certification-addendum.md').write_text(content)
print('ADDENDUM bytes',len((B/'issue-certification-addendum.md').read_bytes()))
