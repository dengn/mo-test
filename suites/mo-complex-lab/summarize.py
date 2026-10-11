import collections,html,json,statistics,time,hashlib,base64
from pathlib import Path
import numpy as np
from data import ROOT
from scenarios import SQL,SCIENCE,sql_for,label

def main():
 p=ROOT/'results/canonical';meta=json.loads((p/'meta.json').read_text());by=collections.defaultdict(collections.Counter);byclient=collections.defaultdict(collections.Counter);timings=collections.defaultdict(list);failed=[];seen=set();representatives={};families={};query=[];oracle=[];compute=[]
 with (ROOT/'cases.jsonl').open('w') as allcases,(ROOT/'failures.jsonl').open('w') as ff:
  for f in sorted(p.glob('cases-*.jsonl')):
   for line in f.open():
    r=json.loads(line);case=r['case_id'];assert case not in seen;seen.add(case);allcases.write(line)
    by[r['category']][r['status']]+=1;byclient[r['client']][r['status']]+=1
    families.setdefault(r['family'],collections.Counter())[r['status']]+=1
    if r['status']=='pass':timings[r['family']].append(r['query_ms']);query.append(r['query_ms']);oracle.append(r['oracle_ms']);compute.append(r['compute_ms'])
    else:
     ff.write(line);failed.append(r);representatives.setdefault((r['family'],r['status']),r)
 assert seen==set(range(100000)),(len(seen),len(set(range(100000))-seen));assert sum(sum(v.values()) for v in by.values())==100000
 def pct(x):return dict(zip(['p50','p95','p99','max'],[round(float(v),3) for v in np.quantile(x,[.5,.95,.99,1])])) if x else {}
 health=[json.loads(x) for x in (p/'health.jsonl').read_text().splitlines()]
 connectors={}
 for name in ['spark','flink']:
  cp=ROOT/'results'/name
  if (cp/'meta.json').exists():
   counts=collections.Counter();unique=set()
   for line in (cp/'cases.jsonl').open():
    r=json.loads(line);assert r['case_id'] not in unique;unique.add(r['case_id']);counts[r['status']]+=1
   assert len(unique)==10000
   connectors[name]={'meta':json.loads((cp/'meta.json').read_text()),'counts':dict(counts),'jobs':json.loads((cp/'jobs.json').read_text())}
 result={'canonical':meta,'by_category':dict(by),'by_client':dict(byclient),'by_family':families,'query_latency_successful_ms':pct(query),'oracle_latency_successful_ms':pct(oracle),'client_compute_latency_ms':pct(compute),'family_query_latency_ms':{k:pct(v) for k,v in timings.items()},'observed_harness_cases_per_second':100000/meta['seconds'],'health':{'samples':len(health),'errors':[r for r in health if r['status']!='ok'],'pids':sorted(set(r['pid'] for r in health)),'peak_rss_mib':max(r.get('rss_mib',0) for r in health)},'supplemental_connectors':connectors,'failure_groups':len(representatives),'data_integrity':json.loads((ROOT/'data-integrity.json').read_text()),'environment':{'build_commit':'23d8f61252f3017dff218b530817a240206fd762','binary_sha256':'49d2d31eeb6c8b3151612aa10314c1081cb47908410e7321fae389b0db0c80e7','version':'8.0.30-MatrixOne-v','cpu_quota':4,'memory_gib':16},'scope_limits':['100 scenario definitions ×1000 parameter tuples, not 100000 unrelated SQL grammars.','SQL-only oracle is DuckDB 1.3.2; six definitions cross-checked with NumPy/Pandas in 168 checks.','Client numerical/ML algorithms run in NumPy; MO provides SQL-derived features. Shared numerical implementation checks data interoperability, not independent algorithm correctness.','Explicit DOUBLE casts used for scientific arithmetic. Initial pilot decimal-scale differences are retained separately and not treated as engine wrong-result defects.','Main workload is read-only on 113830 deterministic rows across nine tables, 24 customers without facts, missing credits and skewed customers.','Local single-instance warm workload and simultaneous local oracle/client CPU use; no distributed HA, crash/restart, production-load or multi-node guarantee.','Query timings are client-visible observations under mixed load, not isolated MO engine benchmarks.']}
 for extra in ['failure-analysis.json','performance.json','stability-extra.json','github-issue-matches.json','server-log-analysis.json','client-setup-notes.json']:
  if (ROOT/extra).exists():result[extra[:-5]]=json.loads((ROOT/extra).read_text())
 (ROOT/'report.json').write_text(json.dumps(result,indent=2));(ROOT/'failure-representatives.json').write_text(json.dumps(list(representatives.values()),indent=2))
 def esc(x):return html.escape(str(x))
 def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+esc(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
 totals=meta['counts'];sections=[]
 sections.append('<p>独立新批次：100 类 × 1000 组参数，全部实际执行并保留逐例结果。80 类复杂 SQL；20 类 SQL 特征读取后由 NumPy 执行数值／模型计算。Spark 和 Flink 为另行统计的复杂 JDBC 补测。</p>')
 sections.append(table(['执行数','通过','SQL 错误','结果差异','测试框架错误','耗时秒'],[[100000,totals.get('pass',0),totals.get('sql_error',0),totals.get('mismatch',0),totals.get('harness_error',0),round(meta['seconds'],2)]]))
 sections.append('<h2>复杂场景覆盖</h2>'+table(['场景类别','通过','SQL 错误','差异','框架错误'],[[k,*[v.get(s,0) for s in ['pass','sql_error','mismatch','harness_error']]] for k,v in by.items()]))
 sections.append('<h2>客户端与独立核对</h2>'+table(['客户端','通过','SQL 错误','差异'],[[k,*[v.get(s,0) for s in ['pass','sql_error','mismatch']]] for k,v in byclient.items()])+'<p>DuckDB 从原始确定性数据构建独立基准。9 张 MO 表逐列全文核对通过；168 项 Pandas／NumPy 交叉校验通过。计数精确比较，浮点绝对／相对容差均为 1e-7。并列窗口显式指定稳定次序；浮点值作为排序键的边界另行复现。</p>')
 sections.append('<h2>失败证据与判定</h2><p><strong>1000 例 SQL 错误来自同一类非等值关联聚合 Top-K 子查询：</strong>明确返回 NYI，相关开放 issue 为 <a href="https://github.com/matrixorigin/matrixone/issues/28298">#28298</a>。<strong>8 例原始结果差异涉及 RFM、CUME_DIST 和序数相关系数：</strong>浮点 SUM 排序键相差最多约 4.55e-13，改变了近似相等值的顺序／并列分组；统一舍入到 6 位后 8 例全部一致。保留原始失败统计，归为浮点排序键可移植性敏感，未证明窗口算法本身有错误。</p>'+table(['场景','状态','案例','错误／预期与实际'],[[r['family'],r['status'],r['case_id'],r.get('error',str(r.get('expected'))+' → '+str(r.get('actual')))[:900]] for r in representatives.values()]))
 if 'failure-analysis' in result:sections.append('<details><summary>展开原始复现、浮点排序键与舍入对照证据</summary><pre>'+esc(json.dumps(result['failure-analysis'],ensure_ascii=False,indent=2))+'</pre></details>')
 sections.append('<h2>延迟与稳定性</h2>'+table(['观察项目','P50 ms','P95 ms','P99 ms','最大 ms'],[[k,*[v.get(z,'') for z in ['p50','p95','p99','max']]] for k,v in [('成功 MO 查询',pct(query)),('独立基准计算',pct(oracle)),('客户端计算',pct(compute))]])+f'<p>混合测试吞吐 {100000/meta["seconds"]:.2f} cases/s；8 个客户端线程。心跳采样 {len(health)} 次，错误 {len(result["health"]["errors"])} 次，PID {esc(result["health"]["pids"])}，峰值 RSS {result["health"]["peak_rss_mib"]:.1f} MiB。</p>')
 if 'performance' in result:
  perf=result['performance']['groups']
  sections.append('<h3>独立复杂查询性能补测</h3>'+table(['并发','查询数','QPS','P50 ms','P95 ms','P99 ms','正确结果'],[[r['concurrency'],r['queries'],round(r['queries_per_second'],2),*[round(r['latency_ms'][k],2) for k in ['p50','p95','p99']],r['counts']] for r in perf])+'<p>多表净额、滚动均值、递归图遍历、多事实客户特征四类混合查询；预热和结果比对均在计时范围外，三轮交错顺序，共 12,288 条查询全部保留耗时和核对状态。</p>')
  if (ROOT/'performance.png').exists():sections.append('<img style="width:100%;height:auto" alt="Complex query throughput and latency by concurrency" src="data:image/png;base64,'+base64.b64encode((ROOT/'performance.png').read_bytes()).decode()+'">')
 sections.append('<h2>Spark / Flink 复杂 JDBC 补测</h2>'+table(['引擎','独立分组断言','通过','Pipeline 错误','差异','耗时秒'],[[k,10000,v['counts'].get('pass',0),v['counts'].get('pipeline_error',0),v['counts'].get('mismatch',0),round(v['meta']['seconds'],2)] for k,v in connectors.items()])+'<p>每引擎 10 个复杂流水线 × 1000 客户：多源 JOIN、退款与支付净额、滚动均值、会话转化、最后触点、活跃 streak、缺失插补、图邻居、衰减归因、渠道熵。源和结果都经 MO JDBC；每个输出由 DuckDB 独立核对。Spark 显式 READ_COMMITTED。两轮 Flink 客户端 SQL 构建失败已保留；改用顶层 Table API CTE 视图、引用 Calcite 保留标识符后，完成上述最终补测。客户端搭建失败不记为 MO 引擎缺陷，Spark/Flink 成功运行均在主测试结束之后。</p>')
 sections.append('<h2>GitHub 跟踪</h2><p><a href="https://github.com/matrixorigin/matrixone/issues/29838">#29838 Spark 默认隔离级别兼容性</a> · <a href="https://github.com/matrixorigin/matrixone/issues/29839">#29839 TANH 支持请求</a>：已按用户要求提交，这两个属于上一批测试发现。</p>')
 if 'github-issue-matches' in result:sections.append('<details><summary>展开新一批问题的已有 issue 核对明细</summary><pre>'+esc(json.dumps(result['github-issue-matches'],ensure_ascii=False,indent=2))+'</pre></details>')
 sections.append('<h2>100 类明细</h2>'+table(['名称','类别','通过','SQL 错误','差异','查询 P95 ms'],[[label(f)[0],label(f)[1],families.get(label(f)[0],{}).get('pass',0),families.get(label(f)[0],{}).get('sql_error',0),families.get(label(f)[0],{}).get('mismatch',0),pct(timings[label(f)[0]]).get('p95','')] for f in range(100)]))
 sections.append('<h2>范围与可复现性</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in result['scope_limits'])+'</ul><p>执行二进制 commit：<code>23d8f61252f3017dff218b530817a240206fd762</code>。环境、数据哈希、SQL、参数、逐例实际／预期值、监控和复现代码见同目录及压缩包。查询错误不会重试后计为通过。</p>')
 doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MatrixOne 复杂数据科学 100000 例实测</title><style>body{font:15px/1.65 system-ui,sans-serif;max-width:1280px;margin:32px auto;padding:0 24px;color:#172435;background:#f5f8fc}h1{font-size:30px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{border:1px solid #d8e1ef;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#dbeafe}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f8;padding:18px;font-size:12px}a{color:#165ea6}</style><h1>MatrixOne 复杂数据科学 100,000 例实测</h1>'+''.join(sections)+'</html>'
 (ROOT/'report.html').write_text(doc);print(json.dumps({'counts':totals,'query':pct(query),'health':result['health'],'connectors':{k:v['counts'] for k,v in connectors.items()}},indent=2))
if __name__=='__main__':main()
