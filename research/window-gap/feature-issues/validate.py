"""Read-only synthetic feature-gap probes with independently checked controls."""
import os,sys,json,subprocess,collections
from pathlib import Path
import numpy as np,duckdb,pandas as pd
from scipy import stats
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent))
from common import connect,read,plain
from rewrites import SQL as REWRITE_SQL,expected as rewritten_expected
SOURCE_ROWS=[(1,1,0,None,2.,1.,1),(2,1,0,2.,4.,2.,0),(3,1,1,4.,3.,1.,1),(4,1,3,4.,7.,3.,1),(5,1,3,None,5.,1.,0),(6,1,8,-1.,8.,2.,1)]
def source():
 out=[]
 for i,g,t,v,y,w,f in SOURCE_ROWS:
  x='NULL' if v is None else str(v)
  out.append(f'SELECT {i} id,{g} gid,{t} tick,CAST({x} AS DOUBLE) v,CAST({y} AS DOUBLE) y,CAST({w} AS DOUBLE) w,{f} flag')
 return '('+' UNION ALL '.join(out)+') fixture'
SOURCE=source();ORDER='PARTITION BY gid ORDER BY id';FRAME=ORDER+' ROWS BETWEEN 2 PRECEDING AND CURRENT ROW'
CASES=[]
def add(key,name,sql,reference=None,expected=None,control=False,reference_engine='DuckDB'):
 CASES.append(dict(issue_key=key,name=name,sql=sql,reference_sql=reference,expected=expected,control=control,reference_engine=reference_engine))
def over(expr,frame=FRAME):return f'SELECT id,{expr} OVER({frame}) result FROM {SOURCE} ORDER BY id'
add('groups','groups',over('SUM(v)','PARTITION BY gid ORDER BY tick GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW'),reference=over('SUM(v)','PARTITION BY gid ORDER BY tick GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW'))
for name in ['CURRENT ROW','GROUP','TIES','NO OTHERS']:
 sql=over('SUM(v)','PARTITION BY gid ORDER BY tick RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW EXCLUDE '+name)
 add('exclude','exclude_'+name.lower().replace(' ','_'),sql,reference=sql)
for fn,args in [('FIRST_VALUE','v'),('LAST_VALUE','v'),('NTH_VALUE','v,2'),('LAG','v,1'),('LEAD','v,1')]:
 sql=over(fn+'('+args+') IGNORE NULLS');ref=over(fn+'('+args+' IGNORE NULLS)')
 add('ignore_nulls',fn.lower()+'_ignore_nulls',sql,reference=ref)
for fn,ref in [('firstNot','FIRST_VALUE(v IGNORE NULLS)'),('lastNot','LAST_VALUE(v IGNORE NULLS)')]:add('ignore_nulls',fn,over(fn+'(v)'),reference=over(ref))
for fn in ['COUNT','SUM','AVG']:
 sql=over(fn+'(DISTINCT v)');add('distinct',fn.lower()+'_distinct',sql,reference=sql)
for fn in ['SUM(v)','COUNT(*)']:
 sql=over(fn+' FILTER(WHERE flag=1)');add('filter',fn+'_filter',sql,reference=sql)
add('filter','sum_case_control',over('SUM(CASE WHEN flag=1 THEN v ELSE NULL END)'),reference=over('SUM(CASE WHEN flag=1 THEN v ELSE NULL END)'),control=True)
for fn in ['lagInFrame','leadInFrame']:
 sql=over(fn+'(v,1,CAST(-99 AS DOUBLE))',ORDER+' ROWS BETWEEN CURRENT ROW AND CURRENT ROW')
 add('frame_navigation',fn,sql,expected=[[float(x[0]),-99.] for x in SOURCE_ROWS],reference_engine='Independent frame membership')
 add('frame_navigation',fn+'_ordinary_control',over(('LAG' if fn=='lagInFrame' else 'LEAD')+'(v,1,CAST(-99 AS DOUBLE))',ORDER+' ROWS BETWEEN CURRENT ROW AND CURRENT ROW'),reference=over(('LAG' if fn=='lagInFrame' else 'LEAD')+'(v,1,CAST(-99 AS DOUBLE))',ORDER+' ROWS BETWEEN CURRENT ROW AND CURRENT ROW'),control=True)
DERIV_SOURCE="(SELECT 1 id,CAST(10 AS DOUBLE) counter,CAST('2024-01-01 00:00:00' AS DATETIME) stamp UNION ALL SELECT 2,CAST(16 AS DOUBLE),CAST('2024-01-01 00:00:02' AS DATETIME) UNION ALL SELECT 3,CAST(5 AS DOUBLE),CAST('2024-01-01 00:00:05' AS DATETIME)) fixture"
add('derivative','nonNegativeDerivative',f'SELECT id,nonNegativeDerivative(counter,stamp) OVER(ORDER BY stamp) result FROM {DERIV_SOURCE} ORDER BY id',expected=[[1.,0.],[2.,3.],[3.,0.]],reference_engine='Independent delta/time calculation')
control=f"WITH a AS (SELECT *,LAG(counter) OVER(ORDER BY stamp) prev,LAG(stamp) OVER(ORDER BY stamp) prev_ts FROM {DERIV_SOURCE}) SELECT id,CASE WHEN prev IS NULL THEN CAST(0 AS DOUBLE) ELSE GREATEST(CAST(0 AS DOUBLE),(counter-prev)/NULLIF(CAST(TIMESTAMPDIFF(SECOND,prev_ts,stamp) AS DOUBLE),0)) END result FROM a ORDER BY id"
add('derivative','delta_time_control',control,expected=[[1.,0.],[2.,3.],[3.,0.]],control=True,reference_engine='Independent delta/time calculation')
profiles={k:[] for k in ['sum2','imin','iminLast','imax','imaxLast','skew','kurtosis','firstNot','lastNot','prod','wavg','wsum','corr','covar','beta','atImax','atImin']}
for j,row in enumerate(SOURCE_ROWS):
 f=SOURCE_ROWS[max(0,j-2):j+1];x=np.array([np.nan if q[3] is None else q[3] for q in f]);y=np.array([q[4] for q in f]);w=np.array([q[5] for q in f]);valid=~np.isnan(x);v=x[valid];vy=y[valid];vw=w[valid];n=len(v);vals={k:np.nan for k in profiles}
 if n:
  mn=np.flatnonzero(x==v.min());mx=np.flatnonzero(x==v.max());vals.update(sum2=float(np.sum(v*v)),imin=int(mn[0]),iminLast=int(mn[-1]),imax=int(mx[0]),imaxLast=int(mx[-1]),firstNot=float(v[0]),lastNot=float(v[-1]),prod=float(np.prod(v)),wavg=float(np.sum(v*vw)/np.sum(vw)),wsum=float(np.sum(v*vw)))
  c2=float(np.sum((v-v.mean())**2));cy2=float(np.sum((vy-vy.mean())**2));cross=float(np.sum((v-v.mean())*(vy-vy.mean())))
  vals.update(skew=float(stats.skew(v,bias=True)) if c2>1e-12 else np.nan,kurtosis=float(stats.kurtosis(v,bias=True,fisher=False)) if c2>1e-12 else np.nan,corr=cross/np.sqrt(c2*cy2) if c2>1e-12 and cy2>1e-12 else np.nan,covar=cross/(n-1) if n>1 else np.nan,beta=cross/c2 if c2>1e-12 else np.nan)
 vals.update(atImax=float(x[np.argmax(y)]),atImin=float(x[np.argmin(y)]))
 for name,value in vals.items():profiles[name].append([float(row[0]),plain(value)])
for name in profiles:
 if name in ['firstNot','lastNot']:continue
 key='weighted' if name in ['wavg','wsum'] else 'pair_stats' if name in ['corr','covar','beta'] else 'moments' if name in ['sum2','skew','kurtosis'] else 'product' if name=='prod' else 'extrema'
 args='v,w' if key=='weighted' else 'v,y' if key=='pair_stats' or name in ['atImax','atImin'] else 'v'
 add(key,name,over(name+'('+args+')'),expected=profiles[name],reference_engine='Independent NumPy/SciPy mathematical profile')
 add(key,name+'_entry',f'SELECT {name}({args}) result FROM {SOURCE}',reference_engine='Name resolution only')
for fn,args in [('max_by','v,y,-id'),('any_value','v')]:
 add('aggregate_over',fn+'_over',over(fn+'('+args+')'),expected=profiles['atImax'] if fn=='max_by' else None,reference_engine='Independent earliest-key argmax' if fn=='max_by' else 'ANY_VALUE has multiple permitted outputs')
 add('aggregate_over',fn+'_aggregate_control',f'SELECT {fn}({args}) result FROM {SOURCE}',expected=[[-1.]],control=True,reference_engine='Largest key is row 6; observed ANY_VALUE representative is row 6')
for fn,args in [('REGR_SLOPE','y,v'),('REGR_INTERCEPT','y,v')]:
 add('regression_existing',fn+'_entry',f'SELECT {fn}({args}) result FROM {SOURCE}',reference_engine='Name resolution only; tracked by #10182')
 add('regression_existing',fn+'_over',over(fn+'('+args+')'),reference_engine='Extension tracked by #10182')
# CH interfaces that currently have no direct dedicated MO entry, with CH's actual signatures.
add('weighted_quantile','quantileExactWeighted_entry',f'SELECT quantileExactWeighted(v,w,0.5) result FROM {SOURCE}',reference_engine='MO entry-absence probe; CH uses parameterized syntax')
add('aggregate_catalog','groupArray_entry',f'SELECT groupArray(v) result FROM {SOURCE}',reference_engine='MO entry-absence probe; ARRAY_AGG compatibility requires separate verification')
for key,names in [('ewm',['ewmMean','ewmVar','ewmStd','ewmCov','ewmCorr']),('topn',['mavgTopN','tmavgTopN','cumavgTopN','movingTopNIndex']),('local_rank',['mrank','tmrank','cumrank']),('valid_windows',['movingWindowIndex','dynamicGroupCumsum','dynamicGroupCumcount']),('technical',['ema','kama','mmaxDrawdown','cumPositiveStreak'])]:
 for name in names:add(key,name+'_entry',f'SELECT {name}(CAST(1 AS DOUBLE),3) result',reference_engine='Dedicated entry name resolution only; not a DolphinDB runtime parity test')
add('moments','sum2_expression_control',over('SUM(v*v)'),expected=profiles['sum2'],control=True,reference_engine='Independent sum of squares')
add('weighted','wsum_expression_control',over('SUM(v*w)'),expected=profiles['wsum'],control=True,reference_engine='Independent weighted sum')
weighted=f'WITH a AS (SELECT id,SUM(v*w) OVER({FRAME}) s,SUM(CASE WHEN v IS NOT NULL THEN w ELSE 0 END) OVER({FRAME}) sw FROM {SOURCE}) SELECT id,s/NULLIF(sw,0) result FROM a ORDER BY id'
add('weighted','wavg_expression_control',weighted,expected=profiles['wavg'],control=True,reference_engine='Independent paired weighted mean')
# Explicit sequential EWM recurrence emulated by a finite historical self-join.
EWMSOURCE='(SELECT 1 id,CAST(1 AS DOUBLE) v UNION ALL SELECT 2,2 UNION ALL SELECT 3,3 UNION ALL SELECT 4,4) fixture'
ewm=f'WITH raw AS (SELECT * FROM {EWMSOURCE}) SELECT a.id,SUM(b.v*CASE WHEN b.id=1 THEN POWER(CAST(0.5 AS DOUBLE),a.id-1) ELSE CAST(0.5 AS DOUBLE)*POWER(CAST(0.5 AS DOUBLE),a.id-b.id) END) result FROM raw a JOIN raw b ON b.id<=a.id GROUP BY a.id ORDER BY a.id'
add('ewm','alpha_half_adjust_false_control',ewm,expected=[[1.,1.],[2.,1.5],[3.,2.25],[4.,3.125]],control=True,reference_engine='Independent recurrence alpha=0.5, adjust=False, no missing values')

def main():
 c=connect();d=duckdb.connect();records=[]
 for case in CASES:
  if case['reference_sql']:
   a=d.execute(case['reference_sql']).fetchdf();case['expected']=plain(a.to_numpy(float))
  for repeat in range(1,4):
   r={**case,'repeat':repeat}
   try:
    a=read(c,case['sql']);actual=plain(a.to_numpy(float));r.update(status='executed',actual=actual)
    if case['expected'] is not None:np.testing.assert_allclose(a.to_numpy(float),np.array(case['expected'],dtype=float),rtol=1e-7,atol=1e-7,equal_nan=True);r['values_verified']=True
   except Exception as ex:
    if isinstance(ex,AssertionError):raise
    r.update(status='rejected',error=str(ex).split('\\n')[0][:1200])
   records.append(r)
   assert (r['status']=='executed')==case['control'],(case['name'],r)
 print('Direct probes',len(records),dict(collections.Counter(r['status'] for r in records)),flush=True)
 # Recheck the actual 17-column SQL workaround; this is full value verification.
 actual=read(c,REWRITE_SQL);gold=rewritten_expected()[list(actual)];np.testing.assert_allclose(actual.to_numpy(float),gold.to_numpy(float),rtol=1e-7,atol=1e-7,equal_nan=True)
 control17=dict(sql=REWRITE_SQL,columns=list(actual),expected=plain(gold.to_numpy(float)),actual=plain(actual.to_numpy(float)),status='pass',scope='Ten-row fixture, frame width four; this verifies declared math profiles, not all DolphinDB options.')
 health=int(read(c,'SELECT 1 healthy').iloc[0,0]);c.close();d.close();assert health==1
 (BASE/'cases.json').write_text(json.dumps(CASES,indent=2,allow_nan=False));(BASE/'validation.json').write_text(json.dumps(dict(records=records,control_all17=control17,health_after=health,scope='All rejected SQL is actually executed three times; positive controls compare complete outputs, not execution status.'),indent=2,allow_nan=False))
 print('All 17 mathematical SQL combinations reverified; subsequent SELECT 1 succeeds.',flush=True)
if __name__=='__main__':main()
