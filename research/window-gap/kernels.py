"""Full registered CH kernel inventory; native mappings and spelling probes are separate."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from probes import connect,mo,ch,expr,FRAME,ORDER

WINDOW_KERNELS={'cume_dist','denseRank','lag','lagInFrame','lead','leadInFrame','nonNegativeDerivative','nth_value','ntile','percentRank','rank','row_number'}
INTERNAL={'aggThrow','nothing','nothingNull','nothingUInt64'}
MAPPING={
 'any_respect_nulls':('FIRST_VALUE(value)','any_respect_nulls(value)'),
 'anyLast_respect_nulls':('LAST_VALUE(value)','anyLast_respect_nulls(value)'),
 'sum':('SUM(value)','sum(value)'), 'avg':('AVG(value)','avg(value)'),
 'count':('COUNT(value)','count(value)'), 'min':('MIN(value)','min(value)'), 'max':('MAX(value)','max(value)'),
 'varPop':('VAR_POP(value)','varPop(value)'), 'varSamp':('VAR_SAMP(value)','varSamp(value)'),
 'stddevPop':('STDDEV_POP(value)','stddevPop(value)'), 'stddevSamp':('STDDEV_SAMP(value)','stddevSamp(value)'),
 'groupBitAnd':('BIT_AND(CAST(value AS BIGINT))','groupBitAnd(CAST(value AS Nullable(Int64)))'),
 'groupBitOr':('BIT_OR(CAST(value AS BIGINT))','groupBitOr(CAST(value AS Nullable(Int64)))'),
 'groupBitXor':('BIT_XOR(CAST(value AS BIGINT))','groupBitXor(CAST(value AS Nullable(Int64)))'),
 'groupConcat':("GROUP_CONCAT(value SEPARATOR '')",'groupConcat(value)'),
 'quantileExactInclusive':('PERCENTILE_CONT(0.3) WITHIN GROUP(ORDER BY value)','quantileExactInclusive(0.3)(value)'),
}
def main():
 rows=[json.loads(l) for l in (ROOT/'results/clickhouse-aggregate-registry.jsonl').open()];canonical=[r for r in rows if not r['alias_to']];assert len(canonical)==207
 c=connect();out=[];mo_names=set(json.loads((ROOT/'sources/mo-function-registry.json').read_text())['names'])
 for r in canonical:
  name=r['name'];item=dict(name=name,source='ClickHouse26.9.16.11 system.functions',kind='window_kernel' if name in WINDOW_KERNELS else 'internal' if name in INTERNAL else 'public_frame_aggregate',mo_same_spelling_registered=name.lower() in mo_names)
  if name in MAPPING:
   mfn,cfn=MAPPING[name];item['mo_mapping']=mfn;item['mo_sql']=expr(mfn);item['mo']=mo(c,item['mo_sql']);item['clickhouse']=ch(expr(cfn));item['classification']='native_candidate_executed' if item['mo']['status']=='executed' and item['clickhouse']['status']=='executed' else 'candidate_rejected'
  elif name in WINDOW_KERNELS:item['classification']='covered_by_window_api_probes'
  elif name in INTERNAL:item['classification']='excluded_debug_or_placeholder'
  else:
   # This is an absence-of-entry probe, not a fake attempt at testing an
   # undocumented multi-argument CH signature. MO registry absence is retained.
   item['mo_sql']=expr(name+'(value)');item['mo']=mo(c,item['mo_sql']);item['classification']='no_direct_native_mapping'
   if name.startswith('uniq') and name!='uniqExact':item['note']='MO has an approximate distinct-count primitive; estimator/precision/state interfaces differ, so no exact kernel equivalence is asserted.'
   if name.startswith('quantile'):item['note']='MO has median/ordered-set percentile/approximate percentile primitives; CH interpolation, weighted, multi-quantile, estimator and state variants are separate native kernels.'
  out.append(item)
 c.close();(ROOT/'results/clickhouse-kernel-matrix.json').write_text(json.dumps(out,indent=2,allow_nan=False));print('Inventory',len(out),'public aggregates',sum(r['kind']=='public_frame_aggregate' for r in out),'native candidates',[(r['name'],r['classification']) for r in out if 'candidate' in r['classification']],flush=True)
if __name__=='__main__':main()
