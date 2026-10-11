import base64,collections,hashlib,html,json,re
from pathlib import Path
import numpy as np
from data import ROOT,SCHEMAS
from graphs import QUESTIONS,query,params

def read(name,default=None):
    p=ROOT/name;return json.loads(p.read_text()) if p.exists() else default

def files(folder):
    return sorted((ROOT/folder).glob('cases-*.jsonl'))

def case_iter(paths):
    for path in paths:
        for line in path.open():
            yield json.loads(line),line

def table(headers,rows):
    cell=lambda v:html.escape(str(v))
    return '<table><thead><tr>'+''.join('<th>'+cell(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'

def main():
    for manifest in ['canonical-code-manifest.json','spark-code-manifest.json']:
        for name,digest in read(manifest,{}).items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,(manifest,name)
    counts=collections.Counter();clients=collections.Counter();by_req=collections.defaultdict(collections.Counter);seen=set();signatures=set();sql_signatures=set();rows=decisions=constraints=steps=0;index=[];lat=[];failures=[]
    with (ROOT/'cases.jsonl').open('w') as master,(ROOT/'failures.jsonl').open('w') as badfile:
        for r,line in case_iter(files('results/canonical')):
            case=r['case_id'];assert case not in seen;seen.add(case);f,i=divmod(case,500);assert r['parameter']==i and r['parameters']==params(i) and r['requirement']==QUESTIONS[f][1]
            assert r['sql']==query(QUESTIONS[f][0],i)
            sql_signatures.add(hashlib.sha256(r['sql'].encode()).hexdigest())
            signatures.add(hashlib.sha256(json.dumps([r['requirement'],r['parameters'],r['sql']],sort_keys=True).encode()).hexdigest());master.write(line)
            counts[r['status']]+=1;clients[r['client']]+=1;by_req[r['requirement']][r['status']]+=1;lat.append(r['ms'])
            if r['status']!='pass':failures.append(r);badfile.write(line)
            model=r.get('actual_analysis',{});rows+=r.get('actual_facts',{}).get('rows',0);decisions+=len(model.get('decisions',[]));constraints+=len(model.get('checks',{}));steps+=len(r.get('publication',[]))
            index.append({'case_id':case,'requirement':r['requirement'],'question':r['question'],'client':r['client'],'status':r['status'],'parameters':r['parameters'],'metrics':model.get('metrics',{}),'checks':model.get('checks',{}),'decision_sample':model.get('decisions',[])[:5],'fact_rows':r.get('actual_facts',{}).get('rows',0),'ms':r['ms']})
    assert seen==set(range(10000));assert len(signatures)==10000
    for f,(d,key,q) in enumerate(QUESTIONS):assert sum(by_req[key].values())==500
    assert clients=={'pandas_sqlalchemy':5000,'pymysql_numpy':5000}
    spark=list(case_iter([ROOT/'results/spark/cases.jsonl']));assert len(spark)==200 and len({r['case_id'] for r,_ in spark})==200
    holistic=list(case_iter(files('results/holistic')));assert len(holistic)==100 and {r['case_id'] for r,_ in holistic}==set(range(100))
    joined=list(case_iter(files('results/joined')));assert len(joined)==50 and {r['case_id'] for r,_ in joined}==set(range(50))
    ml=read('results/spark/native-ml.json');assert len(ml)==20
    for r,_ in spark:
        f,i=divmod(r['case_id'],500);assert r['sql']==query(QUESTIONS[f][0],i);assert r['status']=='pass' and all(r['native_spark_ml']['checks'].values())
    health=[json.loads(line) for line in (ROOT/'results/canonical/health.jsonl').open()]
    report={'canonical':read('results/canonical/meta.json'),'verified_unique_cases':len(seen),'unique_workflow_signatures':len(signatures),'distinct_fact_sql_hashes':len(sql_signatures),'counts':dict(counts),'clients':dict(clients),'by_requirement':{k:dict(v) for k,v in by_req.items()},
        'fact_rows_compared':rows,'decision_rows_compared':decisions,'constraint_checks':constraints,'publication_steps':steps,
        'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,[*np.quantile(lat,[.5,.95,.99]),max(lat)]))),
        'complexity':read('complexity.json'),'health':{'samples':len(health),'errors':[r for r in health if r['status']!='ok'],'pids':sorted({r['pid'] for r in health}),'peak_rss_mib':max(r.get('rss_mib',0) for r in health)},
        'spark':read('results/spark/meta.json'),'spark_guard':read('spark_run-guard.json'),'holistic':read('results/holistic/meta.json'),'joined':read('results/joined/meta.json'),
        'source_audit':read('source-audit-final.json'),'environment':read('environment.json'),'performance':read('performance.json'),'final_state':read('final-state.json'),'log_taxonomy':read('error-taxonomy.json'),'telemetry_analysis':read('telemetry-analysis.json'),
        'scope':{'main':'20 questions ×500 configurations. Each complete case has one 19-table wide fact graph, a scientific decision chain and transaction publication. Native pandas source facts shared per parameter/domain. Every MO graph executed for every main case.',
            'supplement':'200 Spark questions share 20 verified native SQL/ML pipelines, with 200 executor model evaluations and JDBC publications; 100 thirty-source CVaR workflows and 50 single-SQL thirty-table feature stores/allocation plans. All excluded from main 10000.',
            'reference':'Original-data DuckDB, independent pandas multi-table graphs, complete source audits, independent native ML checks. Scientific algorithms are shared between fact paths; independent constraints supplement equality.',
            'numerics':'Raw integral facts exact, continuous 1e-7; model fact inputs round8 and features round10 after raw check; scientific outputs 1e-6; native pandas/NumPy transforms 1e-12.',
            'limitations':'Synthetic, local four CPU/16GiB window; no production forecast/causal/model-validation claim. Binary commit differs from source checkout. Successful fact arrays stored as hashes/samples, fully compared in memory and reproducible from exported inputs.'}}
    (ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));index.sort(key=lambda r:r['case_id']);(ROOT/'case-index.json').write_text(json.dumps(index,ensure_ascii=False))
    complexity=report['complexity'];g=report['spark_guard'];perf=report['performance'];state=report['final_state'];env=report['environment']
    sample=report['telemetry_analysis'].get('current_batch_sample')
    sample_html=(f'<p>从上传失败文件中保留了本轮新库的成功业务请求追踪样本：执行计划 JSON 有效：{sample["exec_plan_valid_json"]}，大小 {sample["exec_plan_bytes"]:,} 字节，上传错误长度匹配：{sample["plan_size_matches_upload_error"]}，超过追踪 TEXT 的 65,535 字节上限。单例证据确认本轮仍存在该容量问题；{state["internal_trace_failed_loads"]} 次内部 LOAD 失败包含旧队列记录，未将全部错误归于本轮请求，也未推断永久丢失。详见 telemetry-analysis.json 和 telemetry/current-batch-oversized-record.json。</p>' if sample else '<p>未保留本轮新库的超限追踪原始记录；内部追踪错误的案例归因存在限制，详见 telemetry-analysis.json。</p>')
    parts=['<h1>MatrixOne 跨域复杂关联与科学计算实测</h1>',
        '<p>20 类业务分析 × 500 组客户、时间、预算、服务水平和风险配置，共 10,000 个主工作流。两条图各关联 19 张不同源表，合计覆盖全部 30 张合成业务表；额外执行 200 个 Spark 场景、100 个跨域长链场景与 50 个单 SQL 关联 30 表的场景。SQL、数据行、约束与模型迭代均不单独计作 case。</p>',
        table(['批次','完整工作流','通过','其他结果'],[['pandas / NumPy 主批次',10000,counts['pass'],10000-counts['pass']],['Spark SQL + ML + 执行器科学计算',200,report['spark']['counts'].get('pass',0),200-report['spark']['counts'].get('pass',0)],['30 表长链 CVaR 经营规划',100,report['holistic']['counts'].get('pass',0),100-report['holistic']['counts'].get('pass',0)],['单 SQL 关联 30 表的特征仓与资源分配',50,report['joined']['counts'].get('pass',0),50-report['joined']['counts'].get('pass',0)]]),
        f'<p>主批次核对 {rows:,} 行事实、{decisions:,} 行决策、{constraints:,} 项业务约束和 {steps:,} 步写回操作。pandas 与 NumPy 各 5,000 例；提交与回滚各 5,000 例。原始 30 表共 284,281 行，执行前后逐表全文核验。</p>',
        '<h2>按需求检索主案例</h2><div class="controls"><label>业务需求 <select id="mission">'+''.join(f'<option value="{k}">{html.escape(q)}</option>' for d,k,q in QUESTIONS)+'</select></label><label>案例 ID <input id="case-id" type="number" min="0" max="9999" value="0"></label></div><pre id="detail"></pre>',
        '<h2>关联与子查询复杂度</h2>',table(['事实图','不同源表','JOIN 节点文本','SELECT 节点文本','EXISTS 节点文本','SQL 字节'],[[d,c['source_count'],c['join_tokens'],c['select_tokens'],c['exists_tokens'],c['sql_bytes']] for d,c in complexity.items() if isinstance(c,dict)]),
        '<p>以上 JOIN/SELECT 数量是可复核的 SQL 文本统计，包含子查询，不代表优化器运行时算子数。窗口去重、时点支付与贷款快照、相关标量子查询、嵌套 NOT EXISTS、IN 与 EXISTS 组合、稀疏购买图、完整日历和分支聚合均用于具体业务语义。</p>',
        '<p>单 SQL 特征仓将客户快照、商品／工厂快照和真实购买桥置于三个嵌套作用域 CTE，再按客户与商品键关联。源表去重数为 30，完整输入按购买粒度核对，并核验独立 pandas 重建、区域／品类 exposure pivot、稳健 PCA、现金／碳排／容量分配，以及事务读回与提交／回滚可见性。</p>',
        '<h2>Spark 原生与执行器路径</h2><p>从 MO JDBC 读取并缓存 30 张源表，在 Spark 中执行完整关联图；接着执行窗口排名、分组统计、join、repartition、标准化、PCA 和 KMeans。通过 grouped pandas 执行，科学模型运行在 Python worker，再用 Spark JDBC 写回 MO。对 worker PID、每行决策以及缩放、PCA 方差／投影／正交性、聚类距离和成员守恒做核验。200 个问题共享 20 个事实与 ML 管线；不将这些内部阶段另计为 case。Spark JDBC 显式使用 READ_COMMITTED，默认隔离兼容问题见已有 <a href="https://github.com/matrixorigin/matrixone/issues/29838">#29838</a>。</p>',
        '<h2>30 表长链场景</h2><p>客户事实 → 贷款校准 → 客户与商品交易桥 → 商品稳健预测 → 市场/供给/设备等跨域因子 → 128 × 14 × 80 相关需求张量 → 信用与供应冲击 → CVaR epigraph 线性规划 → 整数采购 → 现金、能源、碳排及工厂产能核验 → 事务写回。每例对应一套完整经营方案，所有模拟样本仍只计一个场景。合成品类与工厂映射、stockout 校正、风险及未来分布均为显式假设。</p>',
        '<h2>20 类需求及结果</h2>',table(['需求','场景数','通过'],[[q,500,by_req[k]['pass']] for d,k,q in QUESTIONS]),
        '<h2>独立性能测量</h2><p>从兼容性执行中独立测量读取＋科学计算；pandas 还包括原生多表重建。时延排除源快照获取、连接初始化、参考检查和写回；吞吐使用包含调度、连接与释放开销的墙钟时间。每组结果在计时结束后整体核验，避免参考检查与计时中的 worker 争用资源。首轮与源表审计短暂重叠的测量单独归档，只使用审计结束后的重测数据。不是 MO 纯 SQL QPS。</p>',
        table(['客户端','并发','工作流','工作流/秒','P50 ms','P95 ms','P99 ms'],[[x['client'],x['concurrency'],x['workflows'],round(x['workflows_per_second'],2),round(x['latency_ms']['p50'],1),round(x['latency_ms']['p95'],1),round(x['latency_ms']['p99'],1)] for x in perf['groups']]),
        '<img alt="Complex workflow throughput and P95 latency" style="max-width:100%;height:auto" src="data:image/png;base64,'+base64.b64encode((ROOT/'performance.png').read_bytes()).decode()+'">',
        '<h2>精度、客户端问题与稳定性</h2><p>原始未转换的 AVG(integer) 返回定点 scale-four，与 DuckDB/Spark 浮点结果不同；科学计算的 AVG 参数显式转 DOUBLE，未放宽比较阈值，原始记录保存在 attempts。Java 21 与 Arrow direct buffer 的客户端失败保留在 attempts；最终 Spark 使用 Java 17.0.20.1。首次 Spark 正式尝试的 NumPy 核验器将恒定 stockout_rate 的微小舍入残差当作方差，现按恒定输入定义校正为零；先前 30 个成功工作流和失败现场单独归档，最终 200 例全部重新执行。原始 SQL 与源码保留精度契约的修改过程，主批次及最终 Spark 冻结代码哈希已校验。</p>',
        f'<p>健康采样 {len(health)} 次，错误 {len(report["health"]["errors"])}；MO PID 为 {report["health"]["pids"]}，峰值 RSS {report["health"]["peak_rss_mib"]:.1f} MiB。Spark 客户端资源停止原因：{html.escape(str(g["resource_stop_reason"]))}。执行窗内 PANIC/FATAL：{len(state["panic_fatal"])}，所有测试决策工作表为空：{state["all_private_decisions_empty"]}。内部追踪写入失败 {state["internal_trace_failed_loads"]} 次，单独保留证据，不能据此推断业务失败或永久数据丢失。已有相关问题 <a href="https://github.com/matrixorigin/matrixone/issues/29809">#29809</a>、<a href="https://github.com/matrixorigin/matrixone/issues/29797">#29797</a>。</p>',
        table(['ERROR 日志类别','日志条数'],list(report['log_taxonomy']['categories'].items())),
        '<p>日志表统计的是记录条数，一次内部 LOAD 或 ETL 失败可能产生多条上下文记录，不能相加为业务失败数。另有内部 RC 定义变更重试和 TN 调度轮询错误；本轮业务案例与健康检测未表现为失败，但不据此推断每条后台操作均成功恢复。已保留完整执行窗日志和分类样本。</p>',
        sample_html,
        '<h2>基准、环境及复现范围</h2><p>DuckDB 从原始合成输入建立；pandas 独立实现关联事实，Spark 的原生 ML 数值与约束另用 NumPy 核验。科学算法在不同事实路径使用同一实现，物理／预算／概率约束独立核验。原始事实先按 1e-7 核对，再将模型输入规范为 8 位小数、特征算术为 10 位；完整模型按 1e-6 比较。成功事实保存完整数组哈希、列名、样本，所有值在内存逐一核验；输入与代码可以重建完整事实。</p>',
        f'<p>本地 4 CPU / 16 GiB，MO 二进制 commit <code>{env["server_binary_build_commit"]}</code>。工作区源码为不同 commit，未据此替换二进制。合成结果支持兼容性和约束检查，不证明生产环境预测准确率、因果关系或长期稳定性。</p>',
        '<p>交付：cases.jsonl、Spark/长链完整案例、source-audit、SQL 示例、30 表输入、科学模型、代码 SHA256、优化器计划、README 与逐文件哈希清单。</p>']
    payload=json.dumps(index,ensure_ascii=False).replace('</','<\\/');script='''const cases=DATA;const id=document.getElementById('case-id'),mission=document.getElementById('mission'),detail=document.getElementById('detail');function display(n){n=Math.max(0,Math.min(9999,Math.trunc(Number(n)||0)));id.value=n;const c=cases[n];mission.value=c.requirement;detail.textContent=JSON.stringify(c,null,2);}id.addEventListener('input',()=>display(id.value));mission.addEventListener('change',()=>display(cases.find(c=>c.requirement===mission.value).case_id));display(0);'''.replace('DATA',payload)
    css='body{max-width:1360px;margin:40px auto;padding:0 28px;font:16px/1.7 system-ui,sans-serif;color:#192638;background:#f5f8fc}h1{font-size:32px}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:14px;background:white;margin:16px 0}th,td{border:1px solid #cfdaea;padding:9px 12px;text-align:left}th{background:#deebfd}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eaf0f8;padding:18px;max-height:640px;overflow:auto;font:13px/1.5 monospace}select{max-width:850px}input{width:90px}select,input{font:inherit;padding:6px}.controls{display:flex;gap:12px;flex-wrap:wrap}code{overflow-wrap:anywhere}a{color:#2457a7}'
    (ROOT/'report.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MatrixOne 跨域复杂实测</title><style>'+css+'</style><body>'+''.join(parts)+'<script>'+script+'</script></body></html>')
    print(json.dumps({'main':dict(counts),'spark':report['spark']['counts'],'holistic':report['holistic']['counts'],'joined':report['joined']['counts'],'fact_rows':rows,'decision_rows':decisions,'constraints':constraints,'publication_steps':steps},ensure_ascii=False))
if __name__=='__main__':main()
