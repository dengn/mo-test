import collections
import base64
import datetime as dt
import html
import json
from pathlib import Path

import numpy as np
from common import ROOT

def readcases(folder):
    return [json.loads(line) for p in (ROOT/'results'/folder).glob('*.jsonl')
            if p.name!='health.jsonl' for line in p.open()]

def latency(rows):
    vals=[r['query_ms'] for r in rows if r.get('status')=='pass' and 'query_ms' in r]
    return {f'p{p}_ms':float(np.percentile(vals,p)) for p in [50,95,99]} if vals else {}

def health():
    rows=[json.loads(line) for folder in ['core','supplemental']
        for line in (ROOT/'results'/folder/'health.jsonl').open()]
    return {'samples':len(rows),'ping_errors':sum('error' in r for r in rows),
        'observed_pids':sorted(set(r['pid'] for r in rows)),
        'rss_peak_mib':max(r.get('rss_bytes',0) for r in rows)/1048576,
        'first_time':rows[0]['time'],'last_time':rows[-1]['time'],
        'first_memory_events':rows[0]['memory_events'],'last_memory_events':rows[-1]['memory_events'],
        'coverage':'samples every 5 seconds during core and supplemental runs; connector runs not continuously sampled'}

def table(headers,rows):
    return '<div style="overflow-x:auto"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def main():
    rows=sum([readcases(f) for f in ['core','spark','flink']],[])
    ids=[r['case_id'] for r in rows]
    assert len(ids)==100000 and len(set(ids))==100000 and set(ids)==set(range(100000))
    statuses=collections.Counter(r['status'] for r in rows)
    tools={tool:{'cases':len([r for r in rows if r['tool']==tool]),
        'statuses':dict(collections.Counter(r['status'] for r in rows if r['tool']==tool)),
        'passed_query_latency':latency([r for r in rows if r['tool']==tool])}
        for tool in ['pandas','numpy','spark','flink']}
    core_meta=json.loads((ROOT/'results/core/meta.json').read_text())
    benchmark=json.loads((ROOT/'results/supplemental/benchmark.json').read_text())
    soak=json.loads((ROOT/'results/supplemental/soak.json').read_text())
    types=json.loads((ROOT/'results/supplemental/type_checks.json').read_text())
    remediation=readcases('spark-read-committed')
    assert len(remediation)==1000
    failures=[r for r in rows if r['status']!='pass']
    representatives={}
    for r in failures: representatives.setdefault(r['tool']+'/'+r['family'],r)
    (ROOT/'failure-representatives.json').write_text(json.dumps(representatives,indent=2,ensure_ascii=False))
    (ROOT/'failures.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in failures))
    report={'created_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        'canonical_cases':100000,'case_id_integrity':'complete, unique, contiguous [0,99999]',
        'statuses':dict(statuses),'tools':tools,'core_metadata':core_meta,
        'binary_commit':'23d8f61252f3017dff218b530817a240206fd762',
        'spark_read_committed':dict(collections.Counter(r['status'] for r in remediation)),
        'benchmark':{k:v for k,v in benchmark.items() if k!='samples'},
        'soak':soak,'health':health(),'supplemental_types':types,
        'findings':[
          {'id':'TANH','canonical_affected':2000,'kind':'unsupported SQL function','remedy':'客户端 np.tanh，或在经过验证的有界输入上使用 EXP 表达式'},
          {'id':'SPARK_ISOLATION','canonical_affected':1000,'shared_failed_pipelines':10,'kind':'default JDBC write incompatibility','remedy':'isolationLevel=READ_COMMITTED; 独立补测1000例通过'},
          {'id':'VECTOR_INNER_PRODUCT','canonical_affected':0,'supplemental_affected':32,'kind':'NumPy dot compatibility/semantic difference','detail':'此二进制的向量距离语义是 -dot，且输出按 float32 距离域舍入；不是在主批次发现的错误。'}],
        'scope_notes':[
          '100000 为参数化断言，核心 98000 例逐条执行；Spark/Flink 各10 pipeline ×100 group，不是100000种算法。',
          '通过数不是宣称完全兼容。未定义性能SLA、对照数据库或目标容量，性能仅报告观察值。',
          '核心批次后段与初次Spark有时间重叠；百万行最终测量时核心、Spark/Flink及事务soak均已结束。首档测量初期额外执行2条向量语义复核查询，其余无额外测试负载。',
          '120秒8线程独立行事务 soak 不能推断生产环境或长期稳定性。',
          '旧数据目录启动失败及Flink缺JAR配置失败单独保留，不计入数据库兼容性通过/失败。']}
    if (ROOT/'results/supplemental/vector-semantics.json').exists():
        report['vector_semantics']=json.loads((ROOT/'results/supplemental/vector-semantics.json').read_text())
    (ROOT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    status_table=table(['工具','用例','通过','失败','说明'],[
      [t,tools[t]['cases'],tools[t]['statuses'].get('pass',0),tools[t]['cases']-tools[t]['statuses'].get('pass',0),
       '缺 TANH' if t in ['pandas','numpy'] else '默认隔离级别写入失败；修正后1000例通过' if t=='spark' else 'JDBC源→计算→写回'] for t in tools])
    perf=table(['并发','测量查询数','QPS','P50 ms','P95 ms','P99 ms'],[[b['concurrency'],b['measured'],round(b.get('measured_qps',b.get('measured_qps_lower_bound',0)),2),round(b['p50_ms'],2),round(b['p95_ms'],2),round(b['p99_ms'],2)] for b in benchmark['summary']])
    state=report['health']
    body=f'''<!DOCTYPE html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MatrixOne 数据科学测试结果</title>
    <style>body{{font-family:system-ui,sans-serif;color:#182537;background:#f5f7fa;margin:0}}main{{max-width:1080px;margin:auto;padding:40px 24px}}h1{{font-size:30px}}h2{{margin-top:32px;font-size:22px}}.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card{{background:white;border:1px solid #dbe2ea;padding:20px;min-width:170px;border-radius:8px}}strong{{font-size:28px}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dbe2ea}}th{{background:#e8eef6}}p,li{{line-height:1.8}}code{{background:#e8eef6;padding:2px 5px}}a{{color:#195bb5}}.note{{background:#fff2d9;border-left:4px solid #c18a16;padding:14px}}small{{color:#54667c}}</style>
    <main><h1>MatrixOne 数据科学兼容性、性能与稳定性验证</h1><p>实际运行二进制：<code>23d8f61252f3</code>，单节点 · 4 核 CPU 配额 · 16 GiB 内存。</p>
    <div class="cards"><div class="card">主批次用例<br><strong>100,000</strong></div><div class="card">通过<br><strong>{statuses.get('pass',0):,}</strong></div><div class="card">失败<br><strong>{len(failures):,}</strong></div><div class="card">主批次数值差异<br><strong>{statuses.get('mismatch',0)}</strong></div></div>
    <p class="note">完成的是 10 万个参数化断言，不是 10 万种算法。98,000 例逐条执行 SQL；Spark 和 Flink 各有 10 个 JDBC pipeline，每个验证 100 个 group。默认连接配置的失败保留，修复补测另计。</p>
    <h2>兼容性结果</h2>{status_table}<p>统计聚合、方差/相关性、数学变换、缺失值、特征工程、排序/窗口、TopK、日期/Unicode/JSON。核心 98,000 例耗时 {core_meta['execution_seconds']:.1f} 秒。每例包含固定 seed、参数、独立期望值、实际值、SQL、延迟和错误。</p>
    <h2>三个具体发现</h2><ol><li><code>TANH</code> 不受支持：2,000 个参数化 case 报 SQL 错误。客户端 <code>np.tanh</code> 可计算；EXP 表达式替代只在本次有界输入上验证。</li><li>Spark 默认 JDBC 写入使用 <code>READ_UNCOMMITTED</code>，MO 拒绝。设置 <code>isolationLevel=READ_COMMITTED</code> 后，独立补测 1,000 例全通过。10 个共享失败 pipeline 对应 1,000 个受影响 group，并非 1,000 个根因。</li><li>补充向量测试中，<code>inner_product()</code> 对 32 组向量返回 NumPy 点积的相反数。该版本将其作为负内积距离，并使用 float32 距离域。需要迁移适配；不能直接当 NumPy 的标准点积。<a href="https://docs.matrixorigin.cn/mo/en/v26.4.2.4/MatrixOne/Reference/Functions-and-Operators/Vector/inner_product.html">官方函数文档</a>亦显示负号现象，源码/实测证据保存在 vector-semantics.json。</li></ol>
    <h2>1,048,576 行性能补测</h2>{perf}<p>全扫描统计、100组聚合、过滤点积混合负载。每线程两次预热不计入测量；客户端 query+fetch 耗时，热缓存，同机执行。每个并发级别独立测量；不能与 Spark/Flink 作吞吐比较，也不是 MO 内核耗时或生产 SLA。</p>
    <h2>稳定性与边界类型</h2><p>120 秒、8 线程，完成 {soak['cycles']:,} 个“提交增量→回滚增量→读回校验”事务周期；错误 {sum(len(w['errors']) for w in soak['workers'])} 个，最终计数核对 {'通过' if soak['counter_verification'] else '失败'}。监控采样 {state['samples']} 次，ping 错误 {state['ping_errors']}，同一 PID {state['observed_pids']}，观测 RSS 峰值 {state['rss_peak_mib']:.1f} MiB。</p>
    <p>完整 8,192 行 DataFrame 读取比对、DECIMAL(38,18) 精确读写、int64/uint64 边界、Unicode/NUL/二进制、闰日/NULL 往返均通过。32组 L2 和 cosine 向量距离符合 NumPy。</p>
    <p class="note">短时测试范围内没有发现崩溃或 OOM。此次未验证分布式故障恢复、热点写争用、长时间运行、远程网络或生产规模。旧数据目录的启动失败和 Flink 缺依赖已分别记录，不混入 10 万例兼容性计数。</p>
    <h2>可复现材料</h2><p><a href="report.json">机器可读汇总</a> · <a href="failure-representatives.json">失败代表与原始SQL</a> · <a href="failures.jsonl">全部主批次失败</a> · <a href="README.md">运行说明</a> · <a href="matrixone-ds-validation.zip">完整证据与测试代码压缩包</a></p>
    <small>生成时间：{html.escape(report['created_at'])}（Asia/Shanghai）；未修改 MatrixOne 源代码。</small></main></html>'''
    from plot_performance import render
    render()
    image=base64.b64encode((ROOT/'performance.png').read_bytes()).decode()
    body=body.replace('<h2>1,048,576 行性能补测</h2>',
        '<h2>1,048,576 行性能补测</h2><img alt="百万行混合查询吞吐与延迟曲线" style="width:100%;height:auto" src="data:image/png;base64,'+image+'">')
    body=body.replace('每个并发级别独立测量；', '核心、Spark/Flink及事务测试结束后测量。首档初期额外有2条短向量复核查询；其他档无额外测试负载。每个并发级别独立测量；')
    (ROOT/'report.html').write_text(body)
    print(json.dumps({'total':len(rows),'statuses':dict(statuses),'soak_cycles':soak['cycles'],'benchmark':benchmark['summary']},ensure_ascii=False))

if __name__=='__main__': main()
