"""Executable MO/ClickHouse capability probes, independent from the 10000-case count."""
import collections,json,os,re,subprocess,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
from common import connect,read,plain

CH=Path(os.getenv('CLICKHOUSE_BINARY',str(ROOT/'cache/clickhouse')))
ROWS=[(1,1,0,None,2.,1.,1),(2,1,0,2.,4.,2.,0),(3,1,2,4.,3.,1.,1),(4,1,3,4.,7.,3.,1),(5,1,3,None,5.,2.,0),(6,1,7,-1.,8.,1.,1),(7,1,8,3.,9.,2.,0),(8,2,0,1.,2.,1.,1),(9,2,2,None,3.,2.,1),(10,2,4,5.,4.,1.,0)]
def source():
 rows=[]
 for point,eid,tick,value,y,weight,flag in ROWS:
  val='NULL' if value is None else str(value);stamp=f'2024-01-01 00:00:{tick:02d}'
  rows.append(f"SELECT {point} point,{eid} eid,{tick} tick,CAST({val} AS DOUBLE) value,CAST({y} AS DOUBLE) y,CAST({weight} AS DOUBLE) weight,{flag} flag,CAST('{stamp}' AS DATETIME) stamp")
 return '('+' UNION ALL '.join(rows)+') fixture'
SOURCE=source();ORDER='PARTITION BY eid ORDER BY tick,point';FRAME=ORDER+' ROWS BETWEEN 3 PRECEDING AND CURRENT ROW'

def ch(sql):
 # In MO DOUBLE expressions are nullable. CH DOUBLE is nonnullable, so the
 # same NULL fixture needs an explicit Nullable(Float64) type in CH only.
 sql=sql.replace('CAST(NULL AS DOUBLE)','CAST(NULL AS Nullable(Float64))')
 sql=re.sub(r'CAST\(([-+0-9.eE]+) AS DOUBLE\) value',r'CAST(\1 AS Nullable(Float64)) value',sql)
 cmd=[str(CH),'local','--path',str(ROOT/'cache/probes'),'--max_threads','1','--max_memory_usage','536870912','--query',sql+' FORMAT JSONEachRow'];r=subprocess.run(cmd,text=True,capture_output=True,timeout=30)
 if r.returncode:return dict(status='rejected',sql=sql,error=r.stderr[-6000:],returncode=r.returncode)
 return dict(status='executed',sql=sql,rows=[json.loads(l) for l in r.stdout.splitlines() if l.strip()])
def mo(c,sql):
 try:
  frame=read(c,sql);return dict(status='executed',columns=list(frame),rows=plain([dict(zip(frame.columns,r)) for r in frame.itertuples(index=False,name=None)]))
 except Exception as e:return dict(status='rejected',error=str(e)[:6000])

def expr(fn,frame=FRAME):return f'SELECT point,eid,tick,{fn} OVER({frame}) result FROM {SOURCE} ORDER BY eid,point'
def main():
 c=connect();results=[]
 def probe(category,name,sql,ch_sql=None,**extra):
  r=dict(category=category,name=name,mo_sql=sql,**extra);r['mo']=mo(c,sql);r['clickhouse']=ch(ch_sql or sql) if ch_sql is not False else {'status':'not_run','basis':'DolphinDB documentation plus MO execution; no licensed DolphinDB runtime attached'};results.append(r);print(category,name,r['mo']['status'],r['clickhouse']['status'],flush=True);return r
 windows={'row_number':'row_number()','rank':'rank()','dense_rank':'dense_rank()','percent_rank':'percent_rank()','cume_dist':'cume_dist()','ntile':'ntile(3)','first_value':'first_value(value)','last_value':'last_value(value)','nth_value':'nth_value(value,2)','lag':'lag(value,2,NULL)','lead':'lead(value,2,NULL)','lagInFrame':'lagInFrame(value,2,NULL)','leadInFrame':'leadInFrame(value,2,NULL)','nonNegativeDerivative':'nonNegativeDerivative(COALESCE(value,0),stamp)'}
 for name,fn in windows.items():
  frame=ORDER if name in ['lag','lead','percent_rank','cume_dist'] else ORDER+' ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING'
  r=probe('clickhouse_window_api',name,expr(fn,frame))
  if name in ['lag','lead']:
   alternate=expr(f'{name}(value,2,CAST(0 AS DOUBLE))',ORDER);r['mo_typed_default_sql']=alternate;r['mo_typed_default']=mo(c,alternate)
 mapping={
  'sum':'SUM(value)','sum2':None,'avg':'AVG(value)','std':'STDDEV_SAMP(value)','stdp':'STDDEV_POP(value)','var':'VAR_SAMP(value)','varp':'VAR_POP(value)','count':'COUNT(value)','min':'MIN(value)','max':'MAX(value)','med':'MEDIAN(value)',
  'row_number':'ROW_NUMBER()','rank':'RANK()','dense_rank':'DENSE_RANK()','percent_rank':'PERCENT_RANK()','cume_dist':'CUME_DIST()','lead':'LEAD(value,1,NULL)','lag':'LAG(value,1,NULL)','ntile':'NTILE(3)','first_value':'FIRST_VALUE(value)','last_value':'LAST_VALUE(value)','nth_value':'NTH_VALUE(value,2)',
  'percentile':'PERCENTILE_CONT(0.3) WITHIN GROUP(ORDER BY value)',
 }
 catalog=json.loads((ROOT/'dolphindb-catalog.json').read_text())
 binary={'wsum','wavg','corr','covar','beta','atImax','atImin'}
 for name in catalog['sql_analytic_names']:
  fn=mapping.get(name)
  candidate=fn or f'{name}(value,y)' if name in binary else fn or f'{name}(value)'
  if name in ['lag','lead']:candidate=f'{name}(value,1,CAST(0 AS DOUBLE))'
  probe('dolphindb_sql_analytic',name,expr(candidate),False,native_mapping=fn,argument_scope='Default/linear interpolation; additional DolphinDB options evaluated separately')
 for name,frame in [('rows',FRAME),('range_numeric','PARTITION BY eid ORDER BY tick RANGE BETWEEN 2 PRECEDING AND CURRENT ROW'),('groups','PARTITION BY eid ORDER BY tick GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW')]:probe('frame',name,expr('SUM(value)',frame))
 for rule in ['CURRENT ROW','GROUP','TIES','NO OTHERS']:probe('frame','exclude_'+rule.lower().replace(' ','_'),expr('SUM(value)',FRAME+' EXCLUDE '+rule))
 for fn in ['FIRST_VALUE(value)','LAST_VALUE(value)','NTH_VALUE(value,2)','LAG(value,1)','LEAD(value,1)']:
  for modifier in ['IGNORE NULLS','RESPECT NULLS']:probe('null_semantics',fn+' '+modifier,expr(fn+' '+modifier))
 probe('syntax','named_window',f'SELECT point,SUM(value) OVER w result FROM {SOURCE} WINDOW w AS ({FRAME}) ORDER BY eid,point')
 probe('syntax','named_window_inheritance',f'SELECT point,SUM(value) OVER w2 result FROM {SOURCE} WINDOW w AS (PARTITION BY eid),w2 AS (w ORDER BY tick,point ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) ORDER BY eid,point')
 probe('frame','datetime_interval',expr('SUM(value)','PARTITION BY eid ORDER BY stamp RANGE BETWEEN INTERVAL 2 SECOND PRECEDING AND CURRENT ROW'))
 probe('aggregate_semantics','count_distinct',expr('COUNT(DISTINCT value)'))
 probe('aggregate_semantics','filter',f'SELECT point,SUM(value) FILTER(WHERE flag=1) OVER({FRAME}) result FROM {SOURCE} ORDER BY eid,point')
 for name,fn,chfn in [('arg_max','MAX_BY(value,y,point)','argMax(value,y)'),('any_value','ANY_VALUE(value)','any(value)'),('group_concat','GROUP_CONCAT(value)','groupConcat(value)'),('bit_and','BIT_AND(CAST(value AS BIGINT))','groupBitAnd(CAST(value AS Nullable(Int64)))'),('approx_count','APPROX_COUNT_DISTINCT(value)','uniqHLL12(value)'),('median','MEDIAN(value)','quantileExactInclusive(0.5)(value)'),('percentile_linear','PERCENTILE_CONT(0.3) WITHIN GROUP(ORDER BY value)','quantileExactInclusive(0.3)(value)')]:probe('aggregate_semantics',name,expr(fn),expr(chfn))
 # Direct dedicated API absence: SQL spelling probes support the immutable
 # MO registry evidence. They are NOT claims that the underlying math is impossible.
 for row in catalog['named_window_apis']:
  name=row['name'];sql=f'SELECT {name}(CAST(1 AS DOUBLE),3) result';r=dict(category='dolphindb_dedicated_api',name=name,mo_sql=sql,mo=mo(c,sql),source_url=row['url'],families=row['families']);results.append(r)
 c.close();(ROOT/'results/capability-probes.json').write_text(json.dumps(plain(results),indent=2,allow_nan=False));print('PROBES',len(results),dict(collections.Counter((r['category'],r['mo']['status']) for r in results)),flush=True)
if __name__=='__main__':main()
