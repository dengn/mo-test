import base64,collections,hashlib,html,json,os,zipfile
from pathlib import Path
import numpy as np
from data import ROOT
from scenarios import sql_for,label,complexity

def main():
 p=ROOT/'results/canonical';meta=json.loads((p/'meta.json').read_text());seen=set();hashes=set();counts=collections.Counter();byfamily=collections.defaultdict(collections.Counter);byclient=collections.defaultdict(collections.Counter);queries=[];totals=[];oracles=[];sizes=[];ctes=[];joins=[];windows=[];rows=0;stepcounts=[];steptimes=[];commit=rollback=0;reps={};slow=[]
 with (ROOT/'cases.jsonl').open('w') as allrows,(ROOT/'failures.jsonl').open('w') as failed:
  for file in sorted(p.glob('cases-*.jsonl')):
   for line in file.open():
    r=json.loads(line);assert r['case_id'] not in seen;seen.add(r['case_id']);hashes.add(hashlib.sha256(r['sql'].encode()).hexdigest());counts[r['status']]+=1;byfamily[r['family']][r['status']]+=1;byclient[r['client']][r['status']]+=1;allrows.write(line)
    c=r['complexity'];sizes.append(c['sql_bytes']);ctes.append(c['cte_count']);joins.append(c['join_count']);windows.append(c['window_expressions']);rows+=r.get('row_count',0)
    if 'query_ms' in r:queries.append(r['query_ms'])
    oracles.append(r['oracle_ms']);totals.append(r['total_ms']);slow.append((r['total_ms'],r['case_id'],r['family']));slow=sorted(slow,reverse=True)[:10]
    if r.get('steps'):
     stepcounts.append(len(r['steps']));steptimes.extend(s['ms'] for s in r['steps']);commit+=any(s['sql']=='COMMIT' for s in r['steps']);rollback+=not any(s['sql']=='COMMIT' for s in r['steps'])
    if r['status']!='pass':failed.write(line);reps.setdefault((r['family'],r['status']),r)
 assert seen==set(range(10000))
 assert len(hashes)==10000,('SQL generation repeated',len(hashes))
 def stats(a):return dict(zip(['p50','p95','p99','max'],map(float,np.quantile(a,[.5,.95,.99,1])))) if a else {}
 health=[json.loads(l) for l in (p/'health.jsonl').read_text().splitlines()];extra={}
 for name in ['spark','flink','flink-staged','flink-bounded']:
  folder=ROOT/'results'/name
  if (folder/'meta.json').exists():
   e=collections.Counter(json.loads(l)['status'] for l in (folder/'cases.jsonl').open());extra[name]={'counts':dict(e),'meta':json.loads((folder/'meta.json').read_text()),'jobs':json.loads((folder/'jobs.json').read_text())}
 result={'canonical':meta,'verified_case_count':len(seen),'unique_sql_hashes':len(hashes),'counts':dict(counts),'by_client':dict(byclient),'by_family':dict(byfamily),'sql_complexity':{'bytes':stats(sizes),'cte_count':stats(ctes),'joins':stats(joins),'windows':stats(windows)},'observed_latency_ms':{'query':stats(queries),'oracle':stats(oracles),'complete_case':stats(totals),'stage_statement':stats(steptimes)},'result_rows_checked':rows,'multi_stage':{'completed_cases':len(stepcounts),'steps_min':min(stepcounts) if stepcounts else 0,'steps_max':max(stepcounts) if stepcounts else 0,'database_operations':sum(stepcounts),'commit_cases':commit,'rollback_cases':rollback},'health':{'samples':len(health),'errors':[r for r in health if r['status']!='ok'],'pids':list(set(r['pid'] for r in health)),'peak_rss_mib':max(r.get('rss_mib',0) for r in health)},'supplemental_engines':extra,'slowest_cases':slow,'independent_data_check':json.loads((ROOT/'data-integrity.json').read_text()),'scope':{'definition':'50 definitions ×200 parameter tuples: 8000 long SQL reads +2000 staged transactional analyses. Every case executes its own full query; stage operations are not counted as extra cases.','oracle':'DuckDB 1.3.2 built from original deterministic data; numerical tolerance rtol/atol 1e-7; integral counts exact. Full source table comparison plus independently coded market/subscription calculations.','risk_scores':'Synthetic analytical scoring recurrences; not production model validation. Every feedback step changes the output score.','pilot_changes':'Reserved alias RETENTION renamed to active_retention, and activity-island subtraction explicitly casts ROW_NUMBER to signed BIGINT. Initial pilot failures remain separate, not counted in canonical results.','observational_timing':'Main-run query and case times include contention from local DuckDB references and stage/engine work. Isolated measurements, if included, are separate.','stability_limit':'Local single-instance execution window; no HA, crash injection or production-size assurance.','build_commit':'23d8f61252f3017dff218b530817a240206fd762'}}
 for file in ['environment.json','final-state.json','performance.json','failure-analysis.json','client-setup-notes.json','flink-resource-limit.json','flink_staged-guard.json','flink_bounded-guard.json']:
  if (ROOT/file).exists():result[file[:-5]]=json.loads((ROOT/file).read_text())
 (ROOT/'report.json').write_text(json.dumps(result,indent=2));(ROOT/'failure-representatives.json').write_text(json.dumps(list(reps.values()),indent=2))
 esc=lambda x:html.escape(str(x))
 def table(head,items):return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in items)+'</tbody></table>'
 sections=['<p>第三批独立实测：50 类 × 200 组参数。8000 例长 SQL 多场景组合，2000 例中间结果回写、服务器端窗口再分析、提交／回滚与更新回滚。所有原始输入表单独核对。</p>',table(['案例数','通过','SQL 错误','结果差异','阶段差异','框架错误','耗时秒'],[[len(seen),counts['pass'],counts['sql_error'],counts['mismatch'],counts['stage_mismatch'],counts['harness_error'],round(meta['seconds'],2)]])]
 sections+=['<h2>长分析链的实际复杂度</h2>',table(['指标','中位数','P95','最大'],[[k,*[round(v[x],2) for x in ['p50','p95','max']]] for k,v in result['sql_complexity'].items()]),'<p>组合块包括：支付／退款净额、留存和会话转化、衰减多触点归因、补齐日期的滚动时序、回归残差和稳健损失、三跳图邻居、行情滚动方差和回撤、库存风险敞口、投放成本分摊、订阅欠款和复活。每个被选块均参与标准化和连续反馈评分，随后连接 KPI 预算、排序、分组或 grouping sets。</p>']
 sections+=['<h2>多阶段数据库流程</h2>',table(['已完成案例','每例步骤','数据库步骤总数','提交案例','回滚案例'],[[len(stepcounts),f'{min(stepcounts) if stepcounts else 0}–{max(stepcounts) if stepcounts else 0}',sum(stepcounts),commit,rollback]]),'<p>每例先核对长 SQL 提取结果，写入独立工作表，执行窗口变换和再聚合，核对提交／回滚后可见数据；再做 UPDATE、读己写和 ROLLBACK，确认原值恢复，最后清理案例工作行。DuckDB 中间数据由独立基准构建。结束时再次检查全部工作表为空。</p>']
 sections+=['<h2>延迟观察与稳定性</h2>',table(['计时范围','P50 ms','P95 ms','P99 ms','最大 ms'],[[k,*[round(v[x],2) for x in ['p50','p95','p99','max']]] for k,v in result['observed_latency_ms'].items()]),f'<p>心跳 {len(health)} 次，错误 {len(result["health"]["errors"])} 次，PID {esc(result["health"]["pids"])}，峰值 RSS {result["health"]["peak_rss_mib"]:.1f} MiB。主批次属于混合负载观察，不能当作独立引擎吞吐基准。</p>']
 if 'performance' in result:
  groups=result['performance']['groups'];sections+=['<h3>独立长 SQL 并发性能</h3>',table(['并发','测量查询数','QPS','P50 ms','P95 ms','P99 ms','结果'],[[g['concurrency'],g['queries'],round(g['queries_per_second'],2),*[round(g['latency_ms'][k],2) for k in ['p50','p95','p99']],g['counts']] for g in groups])]
  if (ROOT/'performance.png').exists():sections.append('<img style="width:100%" alt="Long SQL throughput and latency" src="data:image/png;base64,'+base64.b64encode((ROOT/'performance.png').read_bytes()).decode()+'">')
 if 'failure-analysis' in result:
  a=result['failure-analysis'];record=a.get('raw_record_evidence') or {}
  sections+=['<h2>内部追踪写入问题：业务结果通过，日志入库失败</h2>',f'<p>主批次期间记录到 {a["internal_trace_failed_load_events"]} 次内部 LOAD DATA INTO system.statement_info 失败事件。保留 CSV 中的一条用户查询状态为 Success，exec_plan 是有效 JSON，但为 {record.get("field_bytes",{}).get("exec_plan","未知")} 字节，超过普通 TEXT 的 65535 字节上限；同一条记录的 statement 仅 {record.get("field_bytes",{}).get("statement","未知")} 字节。与已有 <a href="https://github.com/matrixorigin/matrixone/issues/29797">#29797</a>、<a href="https://github.com/matrixorigin/matrixone/issues/29809">#29809</a> 同类，未重复提单。这个发现单独归为 MO 可观测性缺陷，没有加入业务查询失败计数；不能据此声称记录永久丢失。原始行和失败事件均保留在 telemetry/。</p>']
 sections+=['<h2>Spark / Flink 长链补测</h2>',table(['引擎','额外断言数','通过','Pipeline 错误','差异'],[[name,sum(e['counts'].values()),e['counts'].get('pass',0),e['counts'].get('pipeline_error',0),e['counts'].get('mismatch',0)] for name,e in extra.items()]),'<p>补测独立统计：每个引擎执行两条长组合链，经 MO JDBC 读入 14 个源表、在引擎中计算，再经 JDBC 回写，每条链核对 1000 客户。Spark 显式 READ_COMMITTED，分析器 maxIterations=500；默认上限失败另外保留。Flink 的整条 SQL 规划资源异常与分阶段物化方案分别记录，后者逐块回写并核对，与未物化 DuckDB 程序比较。引擎客户端问题不记为 MO SQL 错误。</p>']
 sections+=['<h2>失败与最慢案例</h2>',table(['类型／案例','证据'],[[r['case_id'],r.get('error',str(r.get('expected'))+' → '+str(r.get('actual')))[:600]] for r in reps.values()]) if reps else '<p>主批次未发现执行失败或核对差异。</p>',table(['完整案例 ms','案例 ID','场景'],[[round(t,2),case,f] for t,case,f in slow])]
 sections+=['<h2>50 类场景</h2>',table(['名称','通过','错误／差异','SQL 字节','CTE','连续反馈层'],[[label(f)[0],byfamily[label(f)[0]]['pass'],sum(byfamily[label(f)[0]].values())-byfamily[label(f)[0]]['pass'],complexity(f,0)['sql_bytes'],complexity(f,0)['cte_count'],complexity(f,0)['feedback_depth']] for f in range(50)])]
 for name in ['environment','final-state','failure-analysis','scope','client-setup-notes','flink-resource-limit','flink_staged-guard','flink_bounded-guard']:
  if name in result:sections.append('<details><summary>'+esc(name)+' 完整证据与范围</summary><pre>'+esc(json.dumps(result[name],ensure_ascii=False,indent=2))+'</pre></details>')
 (ROOT/'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MatrixOne 长分析组合 10000 例实测</title><style>body{font:15px/1.65 system-ui,sans-serif;max-width:1320px;margin:32px auto;padding:0 24px;color:#172435;background:#f5f8fc}h1{font-size:30px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{border:1px solid #d8e1ef;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#dbeafe}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f8;padding:18px;font-size:12px}a{color:#165ea6}</style><h1>MatrixOne 长分析组合 10,000 例实测</h1>'+''.join(sections)+'</html>')
 print(json.dumps({k:result[k] for k in ['counts','unique_sql_hashes','multi_stage','health']},indent=2))
if __name__=='__main__':main()
