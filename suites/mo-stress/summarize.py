import json,datetime,statistics,collections
from pathlib import Path
p=Path('/workspace/mo-stress')
def rows(name):
 result=[]
 for line in (p/name).read_text().splitlines():
  try:result.append(json.loads(line))
  except:pass
 return result
r=rows('results.jsonl');r+=rows('write-results.jsonl') if (p/'write-results.jsonl').exists() else [];resources=rows('resources.jsonl');phases=[x for x in r if x.get('type')=='phase_end'];integrity=[x for x in r if x.get('type')=='integrity']
summary={'commit':'2726fb419b3afa1db2686ae1b2aaca563d1ae214','cpu_quota_cores':4,'memory_limit_gib':32,'phases':phases,'integrity':integrity,'resources':{'peak_server_rss_gib':max((x.get('server_rss_bytes',0) for x in resources),default=0)/1024**3,'peak_cgroup_memory_gib':max((x.get('cgroup_memory_bytes',0) for x in resources),default=0)/1024**3,'peak_server_cpu_cores':max((x.get('server_cpu_cores',0) for x in resources),default=0),'minimum_disk_free_gib':min((x['disk_free_bytes'] for x in resources),default=0)/1024**3,'guard_triggered':any(x.get('guard_triggered') for x in resources),'latest_memory_events':resources[-1].get('memory_events') if resources else None}}

starts={x['phase']:datetime.datetime.fromisoformat(x['time']).timestamp() for x in r if x.get('type')=='phase_start'}
for phase in phases:
 lo=starts[phase['phase']];hi=lo+phase['elapsed_seconds'];samples=[x for x in resources if lo<=x['time_epoch']<=hi]
 phase['resource_samples']={'peak_server_rss_gib':max((x.get('server_rss_bytes',0) for x in samples),default=0)/1024**3,'average_server_cpu_cores':statistics.mean([x['server_cpu_cores'] for x in samples if 'server_cpu_cores' in x]) if samples else 0}
logs=[];cats=collections.Counter();examples={};recovery_errors=[]
logfile=p/('server-load.log' if (p/'server-load.log').exists() else 'server.log')
for line in logfile.read_text().splitlines():
 try:x=json.loads(line);t=datetime.datetime.strptime(x['time'][:19],'%Y/%m/%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
 except:continue
 if t<min(starts.values()) or x.get('level')!='ERROR':continue
 text=x.get('msg','')+' '+x.get('error','')
 if x.get('msg')=='upload files success':kind='success_logged_at_error_level'
 elif 'trigger cron task failed after retries' in text:kind='cron_retry_exhausted'
 elif 'cron task trigger times not match' in text:kind='cron_trigger_mismatch'
 elif any(v in text for v in ('query sql tasks failed','query cron tasks failed','fetch cron tasks')):kind='background_task_fetch_error'
 elif 'commit status is unknown' in text:kind='transaction_commit_unknown'
 elif 'context canceled' in text:kind='request_cancellation'
 elif 'broken pipe' in text or 'connection reset by peer' in text:kind='closed_connection'
 else:kind='other'
 cats[kind]+=1;examples.setdefault(kind,x)
 if kind!='success_logged_at_error_level' and starts.get('recovery',float('inf'))+5<=t<=starts.get('recovery',float('inf'))+60:recovery_errors.append(x)
summary['server_error_logs']={'counts':dict(cats),'examples':examples,'errors_during_low_concurrency_recovery_after_5s':len(recovery_errors)}
(p/'server-errors.json').write_text(json.dumps(summary['server_error_logs'],ensure_ascii=False,indent=2))

(p/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
lines=['# MatrixOne 本地极端负载测试','',f"版本：最新 main 固定提交 `{summary['commit']}`；机器：4 核 CPU 配额，32 GiB 内存。",'', f"结果：共 {sum(x['offered_seconds'] for x in phases)/60:.1f} 分钟、{sum(x['results']['success'] for x in phases):,} 次成功业务操作、{sum(x['results']['errors'] for x in phases)} 次执行超时、{sum(x['results']['cancelled'] for x in phases)} 次阶段结束取消。最高并发 1024。未发生非预期进程退出或 OOM；512/1024 并发已超过这台机器可维持低延迟的处理能力。", '', '数据：200 万行，1024 字节/行的 MD5 重复载荷（逻辑载荷 2,048,000,000 字节，可压缩），10,000 个账户。默认 CPU SIMD 构建。使用独立本地 LOG/TN/CN 实例；未修改源码。','', '混合负载：50% 主键查询、25% 双账户转账事务、15% 追加写入、10% 200 万行连接聚合。分析阶段为纯连接聚合，写压力阶段为 62.5% 转账、37.5% 追加写入。每次查询上限 30 秒；阶段结束取消的请求单独统计。采用闭环客户端，并发是工作线程上限，不表示恒定请求速率。','', '| 阶段 | 并发 | 时长(s) | 成功操作/s | 成功数 | 错误数 | 阶段结束取消 | P50(ms) | P95(ms) | P99(ms) |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for x in phases:
 s=x['results'];l=x['latency_success_ms'];lines.append(f"| {x['phase']} | {x['workers']} | {x['offered_seconds']} | {x['success_ops_per_second']:.2f} | {s['success']} | {s['errors']} | {s['cancelled']} | {l['p50']:.2f} | {l['p95']:.2f} | {l['p99']:.2f} |")
lines+=['','吞吐单位为业务操作/秒；转账包含多条 SQL。延迟分位数只计算成功操作，不涵盖超时/失败请求。阶段结束取消不计为执行错误，但代表未完成工作。','', '资源峰值：',json.dumps(summary['resources'],ensure_ascii=False,indent=2),'', '数据校验：',json.dumps(integrity,ensure_ascii=False,indent=2),'','错误明细：']
for x in phases:
 if x['results']['error_kinds']:lines += [x['phase'],json.dumps(dict(sorted(x['results']['error_kinds'].items(),key=lambda z:z[1],reverse=True)[:20]),ensure_ascii=False,indent=2)]
recovery=p/'crash-recovery.json'
if recovery.exists():lines+=['','异常退出恢复验证：',recovery.read_text()]
lines+=['','服务 ERROR 日志分类（阶段结束取消会产生日志，分类不能视为独立失败请求数）：',json.dumps(dict(cats),ensure_ascii=False,indent=2),f'第一轮降载恢复阶段前 5 秒之后的 ERROR 日志数：{len(recovery_errors)}。已排除内容为 upload files success 的 ERROR 级别日志；完整样本见 server-errors.json。','', '后台 cron 触发不匹配、重试耗尽和任务查询超时表明超载会影响内部调度；不能仅凭客户端成功判定服务完全稳定。此测试尚不能确定这些日志是否存在独立代码缺陷。','', '复现：加载 `source /workspace/matrixone-env.sh`；二进制 `/workspace/matrixone-latest/mo-service`；配置 `/workspace/mo-stress/config/launch.toml`；工作负载源码 `main.go`、原始结果 `results.jsonl`、资源采样 `resources.jsonl`、服务日志 `server.log`。`seed.py` 仅用于新建专用测试数据库，不应在已有库中重复执行。','', '测试范围为此单机、可压缩合成数据和有限时长负载；不代表多节点、真实不可压缩数据、长时间浸泡或生产容量认证。']
(p/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'completed_phases':len(phases),'resources':summary['resources'],'integrity':integrity},ensure_ascii=False))
