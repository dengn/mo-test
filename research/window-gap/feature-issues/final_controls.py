import sys,json
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE.parent))
from validate import SOURCE,FRAME,profiles
from common import connect,read,plain
d=json.loads((BASE/'validation.json').read_text());c=connect();extra=[]
cases=[('ignore_nulls','firstNot_entry',f'SELECT firstNot(v) result FROM {SOURCE}',None,False),('ignore_nulls','lastNot_entry',f'SELECT lastNot(v) result FROM {SOURCE}',None,False),('aggregate_over','max_by_min_key_over',f'SELECT id,max_by(v,-y,-id) OVER({FRAME}) result FROM {SOURCE} ORDER BY id',profiles['atImin'],False),('aggregate_over','max_by_tie_control','SELECT max_by(v,y,-id) oldest,max_by(v,y,id) latest FROM (SELECT 1 id,7 y,2 v UNION ALL SELECT 2,7,9) f',[[2,9]],True)]
work=f'WITH a AS (SELECT id,COUNT(v) OVER({FRAME}) n,AVG(v) OVER({FRAME}) mx,AVG(CASE WHEN v IS NOT NULL THEN y ELSE NULL END) OVER({FRAME}) my,AVG(v*y) OVER({FRAME}) mxy,AVG(v*v) OVER({FRAME}) mx2 FROM {SOURCE}) SELECT id,CASE WHEN ABS(mx2-mx*mx)>1e-12 THEN (mxy-mx*my)/(mx2-mx*mx) ELSE NULL END result FROM a ORDER BY id'
cases.append(('regression_existing','slope_expression_control',work,profiles['beta'],True))
zeros='(SELECT 1 id,CAST(-2 AS DOUBLE) v UNION ALL SELECT 2,0 UNION ALL SELECT 3,3) f'
product=f'WITH a AS (SELECT id,COUNT(v) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) n,SUM(CASE WHEN v=0 THEN 1 ELSE 0 END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) z,SUM(CASE WHEN v<0 THEN 1 ELSE 0 END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) neg,SUM(CASE WHEN v IS NOT NULL AND v<>0 THEN LN(ABS(v)) ELSE CAST(0 AS DOUBLE) END) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) lp FROM {zeros}) SELECT id,CASE WHEN n=0 THEN NULL WHEN z>0 THEN CAST(0 AS DOUBLE) ELSE EXP(lp)*CASE WHEN MOD(neg,2)=0 THEN 1 ELSE -1 END END result FROM a ORDER BY id'
cases.append(('product','zero_and_negative_product_control',product,[[1,-2],[2,0],[3,0]],True))
for key,name,sql,gold,control in cases:
 for repeat in range(1,4):
  r=dict(issue_key=key,name=name,repeat=repeat,sql=sql,expected=gold,control=control)
  try:
   a=read(c,sql);r.update(status='executed',actual=plain(a.to_numpy(float)));np.testing.assert_allclose(a.to_numpy(float),np.array(gold,float),rtol=1e-7,atol=1e-7,equal_nan=True);r['values_verified']=True
  except Exception as e:
   if isinstance(e,AssertionError):raise
   r.update(status='rejected',error=str(e).split('\\n')[0][:1200])
  assert (r['status']=='executed')==control,r;extra.append(r)
assert int(read(c,'SELECT 1').iloc[0,0])==1;c.close();d['records'].extend(extra);(BASE/'validation.json').write_text(json.dumps(d,indent=2,allow_nan=False));print('Added',len(extra),'validated records.')
