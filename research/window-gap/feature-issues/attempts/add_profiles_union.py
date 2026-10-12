import sys,json,subprocess
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE));sys.path.insert(0,'/workspace/mo-window-gap')
from validate import SOURCE,FRAME,ORDER,SOURCE_ROWS,DERIV_SOURCE
from common import connect,read,plain
CH=Path('/workspace/mo-window-gap/cache/clickhouse')
def ch(sql):
 adapted=sql.replace('CAST(NULL AS DOUBLE)','CAST(NULL AS Nullable(Float64))')
 r=subprocess.run([str(CH),'local','--path','/workspace/mo-window-gap/cache/probes','--max_threads','1','--max_memory_usage','536870912','--query',adapted+' FORMAT JSONEachRow'],text=True,capture_output=True,timeout=30)
 assert r.returncode==0,(sql,r.stderr)
 return dict(sql=adapted,rows=[json.loads(x) for x in r.stdout.splitlines() if x.strip()],status='executed')
d=json.loads((BASE/'validation.json').read_text());refs=[]
for name in ['lagInFrame','leadInFrame','nonNegativeDerivative']:
 r=next(r for r in d['records'] if r['name']==name and r['repeat']==1);reference_sql=r['sql']
 if name=='nonNegativeDerivative':reference_sql="SELECT number+1 id, arrayElement([toFloat64(10),toFloat64(16),toFloat64(5)],number+1) counter, toDateTime('2024-01-01 00:00:00')+toIntervalSecond(arrayElement([0,2,5],number+1)) stamp, nonNegativeDerivative(counter,stamp) OVER(ORDER BY stamp) result FROM numbers(3) ORDER BY id"
 actual=ch(reference_sql);got=[[float(x['id']),float(x['result'])] for x in actual['rows']];np.testing.assert_allclose(got,np.array(r['expected'],float),rtol=1e-7,atol=1e-7);refs.append(dict(name=name,shape_note='The same three rows are encoded via numbers/arrays in the CH derivative reference; the UNION literal CH shape returned zeros and is not used as a correctness oracle.' if name=='nonNegativeDerivative' else 'NULL-compatible type adapter only',**actual))
q=f'SELECT quantileExactWeighted(0.5)(v,CAST(w AS UInt64)) result FROM {SOURCE}'
actual=ch(q)
pairs=sorted((r[3],r[5]) for r in SOURCE_ROWS if r[3] is not None);half=sum(w for v,w in pairs)*.5;acc=0;expected=None
for v,w in pairs:
 acc+=w
 if acc>=half:expected=v;break
assert float(actual['rows'][0]['result'])==expected
refs.append(dict(name='quantileExactWeighted',expected=expected,**actual))
# Whole-partition exact unweighted P50 is a supported control; weighting changes the answer.
c=connect();unweighted=read(c,f'SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY v) result FROM {SOURCE}');assert float(unweighted.iloc[0,0])==3.
more=[]
def verify(key,name,sql,gold):
 for repeat in range(1,4):
  a=read(c,sql);np.testing.assert_allclose(a.to_numpy(float),np.array(gold,float),rtol=1e-7,atol=1e-7,equal_nan=True);more.append(dict(issue_key=key,name=name,repeat=repeat,sql=sql,expected=gold,actual=plain(a.to_numpy(float)),status='executed',values_verified=True,control=True))
local=f'WITH raw AS (SELECT * FROM {SOURCE}) SELECT a.id,CASE WHEN a.v IS NULL THEN NULL ELSE 1+SUM(CASE WHEN b.v<a.v THEN 1 ELSE 0 END) END result FROM raw a JOIN raw b ON b.id BETWEEN a.id-2 AND a.id GROUP BY a.id,a.v ORDER BY a.id'
verify('local_rank','local_competition_rank_control',local,[[1,None],[2,1],[3,2],[4,2],[5,None],[6,1]])
topn=f'WITH raw AS (SELECT * FROM {SOURCE}),members AS (SELECT a.id,b.v,ROW_NUMBER() OVER(PARTITION BY a.id ORDER BY b.y DESC,b.id ASC) position FROM raw a JOIN raw b ON b.id BETWEEN a.id-2 AND a.id AND b.v IS NOT NULL),chosen AS (SELECT id,AVG(v) result FROM members WHERE position<=2 GROUP BY id) SELECT a.id,b.result FROM raw a LEFT JOIN chosen b ON a.id=b.id ORDER BY a.id'
gold=[]
for j,r in enumerate(SOURCE_ROWS):
 frame=SOURCE_ROWS[max(0,j-2):j+1];top=sorted([x for x in frame if x[3] is not None],key=lambda x:(-x[4],x[0]))[:2];gold.append([r[0],float(np.mean([x[3] for x in top])) if top else None])
verify('topn','top_two_by_key_average_control',topn,gold)
valid=f'WITH raw AS (SELECT * FROM {SOURCE}),valid_rows AS (SELECT id,v,ROW_NUMBER() OVER(ORDER BY id) ordinal FROM raw WHERE v IS NOT NULL),anchors AS (SELECT a.id,MAX(b.ordinal) current_valid FROM raw a LEFT JOIN valid_rows b ON b.id<=a.id GROUP BY a.id) SELECT a.id,SUM(b.v) result FROM anchors a LEFT JOIN valid_rows b ON b.ordinal BETWEEN a.current_valid-1 AND a.current_valid GROUP BY a.id ORDER BY a.id'
verify('valid_windows','last_two_valid_observations_control',valid,[[1,None],[2,2],[3,6],[4,8],[5,8],[6,3]])
dynamic=f'WITH raw AS (SELECT * FROM {SOURCE}),a AS (SELECT id,v,SUM(flag) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) boundary_group FROM raw) SELECT id,SUM(v) OVER(PARTITION BY boundary_group ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) result FROM a ORDER BY id'
verify('valid_windows','reset_on_flag_cumulative_sum_control',dynamic,[[1,None],[2,2],[3,4],[4,4],[5,4],[6,-1]])
price='(SELECT 1 id,CAST(100 AS DOUBLE) price UNION ALL SELECT 2,120 UNION ALL SELECT 3,90 UNION ALL SELECT 4,110) fixture'
draw=f'WITH a AS (SELECT id,price,MAX(price) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) peak FROM {price}) SELECT id,MAX(CAST(1 AS DOUBLE)-price/peak) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) result FROM a ORDER BY id'
verify('technical','cumulative_max_drawdown_control',draw,[[1,0],[2,0],[3,.25],[4,.25]])
verify('weighted_quantile','unweighted_percentile_control',f'SELECT PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY v) result FROM {SOURCE}',[[3.]])
assert int(read(c,'SELECT 1').iloc[0,0])==1;c.close();d['records'].extend(more);d['clickhouse_controls']=refs;d['weighted_quantile_profile']=dict(weighted_p50=expected,unweighted_p50=3.,scope='Positive integer weights, exact lower weighted CDF threshold, skip NULL values; not all weighted interpolation algorithms.')
(BASE/'validation.json').write_text(json.dumps(d,indent=2,allow_nan=False));print('Added',len(more),'fully verified MO controls and',len(refs),'live ClickHouse controls; weighted P50',expected,'versus unweighted',3.)
