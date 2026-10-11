import json,datetime,collections
from pathlib import Path
p=Path('/workspace/mo-extreme-round2')
files=['results.jsonl','ddl-retry.jsonl','live-results.jsonl','post-crash-audits.jsonl','resumed-results.jsonl','post-fault-writes.jsonl']
records=[]
for name in files:
 if (p/name).exists():
  for line in (p/name).read_text().splitlines():
   try:x=json.loads(line);x['source']=name;records.append(x)
   except:pass
resources=[]
for line in (p/'resources.jsonl').read_text().splitlines():
 try:resources.append(json.loads(line))
 except:pass
ph=[x for x in records if x.get('type')=='scenario_end'];audits=[x for x in records if x.get('type')=='audit'];probes=[x for x in records if x.get('type')=='probe']
summary={'commit':'2726fb419b3afa1db2686ae1b2aaca563d1ae214','machine':{'cpu_quota_cores':4,'memory_gib':32,'client_and_server_share_quota':True},'scenarios':ph,'audits':audits,'probes':probes,'resource':{'peak_server_rss_gib':max((x.get('server',{}).get('rss_bytes',0) for x in resources),default=0)/1024**3,'peak_cgroup_memory_gib':max((x['memory_bytes'] for x in resources),default=0)/1024**3,'min_disk_free_gib':min((x['disk_free_bytes'] for x in resources),default=0)/1024**3,'peak_server_goroutines':max((x.get('metrics',{}).get('go_goroutines',0) for x in resources),default=0),'guard_triggered':any(x.get('resource_guard') for x in resources),'latest_memory_events':resources[-1].get('memory_events') if resources else None}}
for file,key in [('sort-baseline.json','sort_baseline'),('active-fault.json','first_active_fault'),('manual-recovery.json','manual_recovery'),('active-fault-lock-aware.json','second_active_fault')]:
 if (p/file).exists():summary[key]=json.loads((p/file).read_text())
cut=summary.get('first_active_fault',{}).get('cut_epoch');ready=summary.get('manual_recovery',{}).get('ready_epoch')
if cut and ready:summary['first_fault_observed_outage_seconds_including_diagnosis']=ready-cut
(p/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
lines=['# MatrixOne 第二轮极端场景测试','', '固定版本：main `2726fb419b3afa1db2686ae1b2aaca563d1ae214`。4 核、32 GiB；客户端与数据库共用此限额。使用专用数据库，保留上一轮数据；仓库源码未修改。','', '结论：热点事务、死锁中止回滚、连接风暴、取消后的恢复、删除重插、状态感知 DDL，以及故障恢复后的数据核对均得到验证。宽字段排序在 16 并发与 15 秒请求期限下全部超时；单并发同一查询可完成。第一次写入中强制退出后的立即重启失败；等待并重试后恢复。第二次在确认系统锁可获取后重启成功。不能将整轮测试描述为全部无错误。','', '| 场景 | 并发 | 时长(s) | 成功操作数 | 失败/主动取消数 | 阶段结束取消 | 成功操作/s | 全部尝试 P99(ms) |','|---|---:|---:|---:|---:|---:|---:|---:|']
for x in ph:lines.append(f"| {x['scenario']} | {x['workers']} | {x['offered_seconds']} | {x['success']} | {x['errors']} | {x['teardown_cancelled']} | {x['success_ops_per_second']:.2f} | {x['latency_all_attempts_ms']['p99']:.2f} |")
lines+=['', '计数说明：反向加锁场景的死锁中止是预期冲突检测；取消场景使用 100ms 客户端期限，14,227 次主动取消不属于非预期服务错误。写入中故障场景的拒绝连接、无效连接和故障窗口超时与注入故障有关。阶段结束取消单列。P99 包含成功及失败尝试，不能与上一轮仅计算成功请求的 P99 直接比较。','', '每个删除重插事务原子地删除并重插 500 行。载荷为独立伪随机 1536 字节的 Base64 编码（2048 字符），400 个批次共 20 万行，409,600,000 字节逻辑载荷；每行存储 MD5 摘要。反复重写会增加日志和历史版本，不等于增长净逻辑数据量。','', '数据正确性验证：每个成功提交转账的 ID 写入客户端独立日志，校验全部已确认 ID 存在；逐行遍历账本并重建每个账户预期余额；同时校验总余额。随机载荷在种子写入、删除重插、排序、DDL、崩溃恢复后校验行数、主键总和、长度总和和逐行 MD5。']
for x in audits:lines.append('- '+json.dumps(x,ensure_ascii=False))
lines+=['', '宽字段排序：16 并发每次查询读取并排序 20 万个 2 KiB 键、返回前 10 万个主键。15 秒期限下 0 完成、80 超时，负载后恢复查询通过。单并发返回 100,000 个唯一合法主键，耗时 '+str(round(summary.get('sort_baseline',{}).get('elapsed_seconds',0),3))+' 秒。这里验证了功能与过载退化，没有宣称高并发排序可用。','', 'DDL：原始非幂等脚本先添加列、再删除列；第一次添加超时但列实际存在，随后 4,323 次同名添加产生重复列错误。此计数由脚本盲重试放大，不能视为 4,323 次独立数据库缺陷。修改为每次 SHOW COLUMNS 检查实际状态后添加或删除，16 个并发读取客户端下成功完成 22 次变更，无执行错误，数据校验通过。最初超时后的提交状态仍然具有不确定性，业务方需要状态核对。','', '活跃写入故障：第一轮强制退出后首次启动 panic: failed to lock data directory，120 秒故障窗口内未恢复，自动审计因连接拒绝而未执行（不是数据丢失证据）。确认无存活 MO 进程、保留失败日志，等待并重新启动后服务恢复；没有删除锁文件或数据文件。随后逐笔核对 45,395 个已确认提交，无缺失。首次失败根因未被完全确认，可能涉及立即重启时的锁释放时序。第二轮复测额外检查 POSIX fcntl 与 flock 锁可获取，关闭探测句柄后启动实例；结果如下：',json.dumps(summary.get('second_active_fault',{}),ensure_ascii=False,indent=2),'', '首次故障从注入到观察到功能恢复约 '+str(round(summary.get('first_fault_observed_outage_seconds_including_diagnosis',0),1))+' 秒，包含诊断和手动重试时间，不能作为数据库自动恢复延迟。第二次按探测脚本测量；客户端自动重连恢复写入，随后追加正常续写验证。','', '资源：',json.dumps(summary['resource'],ensure_ascii=False,indent=2),'', '资源采样局限：5 秒采样，部分新进程 /proc/fd 访问受限，使用指标端点补充；这些权限缺失不等于进程故障。Go 堆和 RSS 在负载后会保留缓存，本次短时测试不足以证明不存在长期泄漏。','', '复现文件：scenarios.go、sort-baseline.py、active-crash.py、active-crash-lock-aware.py、monitor.py；scenarios-fixed 子命令 all（默认）、ddl_retry、live（仅一次初始化）、audit_live、resume_live normal。数据库名存储于 database.txt；初始化子命令只应在新的独立测试目录执行，不应覆盖已有表。故障脚本仅针对 /workspace/mo-stress/server.pid 中、命令确认为 mo-service 的自有测试进程。第一次失败日志见 restart-first-failure.log。','', '这是一轮有限时长的单机故障与负载测试，不涵盖多节点网络分区、硬件断电、长期磁盘耗尽或 24 小时浸泡测试。']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'completed_scenarios':len(ph),'audit_records':len(audits),'resource':summary['resource']},ensure_ascii=False))
