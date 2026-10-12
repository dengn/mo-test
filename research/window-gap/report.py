"""Compute explicit, reproducible gap counts; keep API absence separate from math."""
import collections,csv,datetime,html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CORE_NATIVE={'avg','count','max','min','med','percentile','std','stdp','sum','var','varp','first','last'}
def main():
 probes=json.loads((ROOT/'results/capability-probes.json').read_text());kernels=json.loads((ROOT/'results/clickhouse-kernel-matrix.json').read_text());ddb=json.loads((ROOT/'dolphindb-catalog.json').read_text());window=[r for r in probes if r['category']=='clickhouse_window_api'];sql=[r for r in probes if r['category']=='dolphindb_sql_analytic']
 missing_window=[r['name'] for r in window if r['mo']['status']!='executed' and r.get('mo_typed_default',{}).get('status')!='executed'];assert missing_window==['lagInFrame','leadInFrame','nonNegativeDerivative']
 missing_sql=[r['name'] for r in sql if r['mo']['status']!='executed'];assert len(missing_sql)==17
 ops={}
 for row in ddb['named_window_apis']:
  name=row['name'];op=name[3:] if name.startswith('cum') else name[2:] if name.startswith('tm') else name[1:] if name.startswith('m') and name not in ['ma','movingWindowIndex','movingTopNIndex'] else name
  ops.setdefault(op,[]).append(name)
 assert len(ops)==78
 api=[r for r in probes if r['category']=='dolphindb_dedicated_api'];assert len(api)==152 and all(r['mo']['status']=='rejected' for r in api)
 public=[r for r in kernels if r['kind']=='public_frame_aggregate'];native=[r for r in public if r['classification']=='native_candidate_executed'];assert len(public)==191 and len(native)==16
 rewrite=json.loads((ROOT/'results/rewrites-all17.json').read_text());assert rewrite['status']=='pass'
 tw=json.loads((ROOT/'results/native-mo-time-windows.json').read_text());assert all(r['status']=='executed' for r in tw)
 summary=dict(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),mo_binary_commit='23d8f61252f3017dff218b530817a240206fd762',clickhouse_version='26.9.16.11 official build',dolphindb_basis='Current official documentation retrieved 2026-10-11/12; 3.00.5 tutorial cross-reference; no live DolphinDB runtime. No claim of live DolphinDB version/performance parity.',clickhouse_window=dict(total=14,implemented_in_mo=11,missing=3,missing_names=missing_window,null_default_bug='LAG/LEAD exist; explicit untyped NULL default can trigger recovered vector panic across partitions; typed NULL executes but returns wrong zero in the final one-row partition; omitting the default is correct on this fixture. Issue #29925.'),dolphindb_sql_over=dict(total=39,native_mappings_executed=22,missing_dedicated=17,missing_names=missing_sql,all17_declared_math_profiles_rewritten_and_verified=True),clickhouse_registered_kernels=dict(registrations_including_aliases=259,canonical=207,window_only_canonical=12,excluded_debug_placeholder=4,public_frame_aggregates=191,explicit_direct_native_candidates_executed=16,no_one_to_one_dedicated_mapping=175,meaning='175 counts distinct registered native kernel implementations, including estimator/interpolation/parameter/state variants and non-time-series domains. It is NOT 175 impossible mathematical calculations. No performance equivalence implied.'),dolphindb_window_apis=dict(named_apis=152,same_named_native_mo_apis=0,normalized_operator_families=78,basic_native_kernel_families=len(CORE_NATIVE),no_one_to_one_specialized_family=len(ops)-len(CORE_NATIVE),meaning='Namespace/API count and prefix-normalized operator count. Native basic kernels still need frame-boundary/minPeriods/null/tie adaptations; no all-option equivalence or streaming-performance equivalence asserted.'),mo_native_time_windows=dict(tumble=True,sliding=True,fill_prev=True,fill_next=True,fill_linear=True,fill_constant=True,boundary_form='_wstart/_wend pseudocolumns in this binary; function-call spelling from some documentation examples rejected'),probe_count=len(probes),sources_manifest='sources/manifest.json')
 (ROOT/'report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n');(ROOT/'operator-families.json').write_text(json.dumps([dict(operator=k,apis=v,classification='basic_native_kernel_with_semantic_adaptation' if k in CORE_NATIVE else 'no_one_to_one_specialized_kernel') for k,v in sorted(ops.items())],indent=2))
 rows=[]
 for r in window+sql:
  implemented=r['mo']['status']=='executed' or r.get('mo_typed_default',{}).get('status')=='executed';rows.append(dict(scope=r['category'],name=r['name'],mo='implemented' if implemented else 'missing_dedicated_entry',mo_runtime=r['mo']['status'],note='untyped NULL default triggers recovered panic; typed NULL returns wrong zero; see #29925' if r['name'] in ['lag','lead'] and r['category']=='clickhouse_window_api' else '',sql=r['mo_sql']))
 with (ROOT/'comparison.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
 # A short authored narrative; raw source pages are excluded from publication.
 for r in native:
  a=r['mo']['rows'];b=r['clickhouse']['rows'];same=len(a)==len(b)
  for ra,rb in zip(a,b):
   for key,x in ra.items():
    y=rb.get(key)
    same=same and (abs(x-y)<=1e-7+1e-7*abs(x) if isinstance(x,(int,float)) and isinstance(y,(int,float)) else x==y)
  r['declared_fixture_values_match']=same
 (ROOT/'results/clickhouse-kernel-matrix.json').write_text(json.dumps(kernels,indent=2,allow_nan=False))
 value_differences=[r['name'] for r in native if r.get('declared_fixture_values_match') is False]
 summary['clickhouse_registered_kernels']['native_candidate_fixture_value_differences']=value_differences
 (ROOT/'report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
 body=f'''# ClickHouse / DolphinDB 与 MatrixOne 窗口计算能力对照

以实际运行的 MO commit `23d8f61252f3017dff218b530817a240206fd762` 为基准。ClickHouse 使用固定官方二进制 **26.9.16.11**，运行只读本地 SQL；DolphinDB 依据抓取时的官方文档和 3.00.5 教程，不声称已实测 DolphinDB 服务。接口存在、参数兼容、数学可组合与专用增量执行内核分别统计。

|口径|对方范围|MO 原生对应|缺少专用对应|
|---|---:|---:|---:|
|ClickHouse 文档列出的窗口入口|14|11|**3**|
|DolphinDB SQL `OVER` 函数|39|22|**17**|
|ClickHouse 规范公开窗口聚合内核|191|16 个明确原生候选执行通过|175 个没有一对一专用映射|
|DolphinDB 专用移动/时间/累计/TopN/技术指标 API|152|0 个同名 API|152 个接口需要适配|
|DolphinDB 上述 API 仅归并 m/tm/cum 前缀后的算子族|78|13 个基础内核族|65 个无一对一专用内核族|

第三行计的是实现/算法/状态变体，包含分位数不同算法、加权与多分位形式及其他领域聚合；不能解释为 175 项业务不可计算。16 个原生候选是“能够执行”，不是“所有行为完全兼容”：其中 {', '.join(value_differences)} 的全 NULL 框架身份值/NULL 输出与符号约定存在差异，完整值均保留。最后两行也不等价于 152/65 种无法在 MO 计算的数学公式。13 个基础族的接口边界、NULL 和最小样本数仍需适配。

ClickHouse 的三个额外窗口入口为 **lagInFrame、leadInFrame、nonNegativeDerivative**。MO 已实现标准的 ROW_NUMBER/RANK/DENSE_RANK/PERCENT_RANK/CUME_DIST/NTILE/FIRST_VALUE/LAST_VALUE/NTH_VALUE/LAG/LEAD；这不保证每种参数组合没有缺陷。依据：[官方窗口入口列表](https://clickhouse.com/docs/reference/functions/window-functions)，[固定版本](https://github.com/ClickHouse/ClickHouse/releases/tag/v26.9.16.11-stable)。

DolphinDB 缺少直接原生映射的 17 个 SQL 入口：**{', '.join(missing_sql)}**。其余 22 个按标准窗口、方差/标准差别名、中位数和线性分位数进行显式映射。`percentile` 的额外插值模式不等同于 MO 的默认线性 ordered-set 分位数。依据：[DolphinDB SQL 分析函数完整表](https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html)。

对这 17 项，我们已在 MO 中组合实现一个明确的常见数学配置，并对全部输出使用原始十行 fixture 的 NumPy/SciPy 独立核验通过，包括相对窗口位置、最早并列、NULL 跳过、有偏偏度、Pearson 峰度和样本协方差。代码为 `rewrites.py`，SQL/完整预期与实际结果在 `results/rewrites-all17.*`。这证明该配置可算；不证明 DolphinDB 的所有参数、矩阵/数组、特殊值、增量复杂度与性能等价。

实测共同窗口之外的缺口包括 **GROUPS 框架、IGNORE NULLS（FIRST/LAST/NTH/LAG/LEAD）、窗口内 DISTINCT、FILTER 聚合子句**。当前 ClickHouse 版本同样拒绝 EXCLUDE；因此新时序场景中的 EXCLUDE 失败不能算作 MO 相对 ClickHouse 独有的差距。MO 的命名窗口及继承通过；DateTime RANGE 的 INTERVAL 偏移在 MO 通过而此 ClickHouse 版本拒绝，不能漏记 MO 已有能力。

**执行缺陷：**三行、两分区的 `LAG(value,1,NULL)` / `LEAD(value,1,NULL)` 会在 MO 返回 20101，包含 `index out of range [2] with length 1` 的恢复型 panic。`CAST(NULL AS DOUBLE)` 执行成功但最后分区错误返回 0；省略默认参数在此 fixture 返回正确 NULL。ClickHouse 对应三行查询正常。`results/null-default-repro.json` 保存原记录，详见 CORRECTIONS.md；已提交 [#29925](https://github.com/matrixorigin/matrixone/issues/29925)。此缺陷不从“11 个已实现入口”扣掉，但必须进入兼容性结论。

**时序专用能力：**MO 已实测支持原生 INTERVAL、SLIDING 和 PREV/NEXT/LINEAR/VALUE 填充，不能写成“MO 没有时间窗口”。本二进制使用 `_wstart` / `_wend` 伪列；文档中部分 `_wstart(ts)` 形式被拒绝。依据：[MO 时间窗口](https://docs.matrixorigin.cn/mo/zh/latest/MatrixOne/Develop/read-data/window-function/time-window.html)，执行记录 `results/native-mo-time-windows.json`。

迁移 DolphinDB 必须逐项处理：m/tm/cum 的边界和输出维度；`minPeriods` 默认值；tm 系列的左开右闭窗口；同时间戳记录的当前可见范围；mrank 的局部窗口排名与 SQL RANK 的整个分区排名；TopN 的 oldest/latest/all 并列策略；样本/总体方差；Pearson/超额峰度；EWM 的 adjust/ignoreNA/时间权重。普通 RANGE/SUM 的可算性不等价于专用增量算子的复杂度和有状态流执行能力。依据：[移动窗口](https://docs.dolphindb.com/en/Functions/Themes/mFunctions.html)、[时间窗口](https://docs.dolphindb.com/en/Functions/Themes/tmFunctions.html)、[累计窗口](https://docs.dolphindb.com/en/Functions/Themes/cumFunctions.html)、[TopN](https://docs.dolphindb.com/en/Functions/Themes/mTopN.html)、[EWM](https://docs.dolphindb.com/en/Functions/e/ewmMean.html)。

优先级建议：先修三行可复现的 NULL 默认参数执行错误；然后补 GROUPS / IGNORE NULLS / DISTINCT 窗口及 FILTER 语义；再按需求补滚动相关/协方差/回归、加权统计、局部 rank/分位数/TopN、EWM 和极值位置。更后面是有状态增量执行、事件时间水位、跨窗口更新和流引擎接口。业务 ROI 应在同数据、同参数、同正确性规则的隔离性能测量后判断，本次没有跨库性能结论。

完整可检查材料：`report.json`、`comparison.csv`、`dolphindb-catalog.json`、`operator-families.json`、固定 ClickHouse 注册表及 `results/clickhouse-kernel-matrix.json`、{len(probes)} 条主要能力探针、17 项组合数学复核和原生时间窗口记录。来源元数据记录 URL/抓取时间/可下载页的 SHA256；ClickHouse 网站原始抓取返回 403，但通过官方网页浏览与固定二进制注册表/实测完成交叉验证。原始网页只在本地缓存，不上传全文。内部调试和占位内核、通用行向量函数、插件和流引擎不混入上述函数数。
'''
 (ROOT/'README.md').write_text(body)
 html_rows=''.join('<tr><td>'+html.escape(r['scope'])+'</td><td>'+html.escape(r['name'])+'</td><td>'+r['mo']+'</td><td>'+html.escape(r['note'])+'</td></tr>' for r in rows)
 page='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MO 窗口能力差距</title><style>body{font:16px/1.7 system-ui;color:#172c3d;background:#f4f7fb;margin:0;overflow-wrap:anywhere}main{max-width:1200px;margin:auto;padding:24px;min-width:0}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{padding:20px;background:white;border:1px solid #dae4ed;border-radius:12px}.card strong{font-size:30px}input{padding:10px;width:min(90%,500px)}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border-bottom:1px solid #dee4e9;text-align:left}.scroll{overflow:auto}pre{white-space:pre-wrap;background:white;padding:20px}</style><main><h1>MatrixOne 窗口计算能力对照</h1><p>MO 23d8f612 · ClickHouse 26.9.16.11 实测 · DolphinDB 官方文档 + MO 探针</p><div class="cards"><div class="card">ClickHouse 窗口入口缺口<br><strong>3 / 14</strong></div><div class="card">DolphinDB SQL 原生入口缺口<br><strong>17 / 39</strong></div><div class="card">DolphinDB 专用 API（需适配）<br><strong>152</strong></div></div><p>实现入口、参数语义、可用 SQL 组合的数学能力与有状态内核分开统计。17 个缺少专用入口的常见数学配置已用 MO 组合实现并独立核验，不能解释为业务不可算。</p><p><a href="README.md">完整研究说明与官方来源</a> · <a href="report.json">计数口径</a> · <a href="comparison.csv">导出映射表</a> · <a href="results/capability-probes.json">执行证据</a></p><input id="search" aria-label="筛选函数" placeholder="筛选函数名或缺口"><span id="count"></span><div class="scroll"><table><thead><tr><th>范围</th><th>函数</th><th>MO</th><th>备注</th></tr></thead><tbody>'''+html_rows+'''</tbody></table></div><h2>不能遗漏的执行差异</h2><p>GROUPS、IGNORE NULLS、窗口 DISTINCT、FILTER 缺口已执行确认。EXCLUDE 同时被两库拒绝。MO 支持命名窗口继承、DateTime INTERVAL RANGE 与原生时序降采样/填充。</p><p>LAG/LEAD 已实现，但跨分区的显式无类型 NULL 默认值可返回查询级 panic。typed NULL 执行成功但最后分区错误返回 0；省略默认参数在此 fixture 正确。服务没有因此退出。详见 <a href="https://github.com/matrixorigin/matrixone/issues/29925">#29925</a> 与 <a href="CORRECTIONS.md">结果更正</a>。</p></main><script>const rows=[...document.querySelectorAll('tbody tr')];const update=()=>{let n=0;const q=document.querySelector('#search').value.toLowerCase();for(const r of rows){const show=r.textContent.toLowerCase().includes(q);r.hidden=!show;if(show)n++}document.querySelector('#count').textContent=' '+n+' / '+rows.length};document.querySelector('#search').addEventListener('input',update);update();</script></html>'''
 (ROOT/'report.html').write_text(page);print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
