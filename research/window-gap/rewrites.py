"""Prove selected common math profiles of all 17 missing DDB SQL primitives in MO."""
import json,warnings
import numpy as np,pandas as pd
from scipy import stats
from common import connect,read,plain
from probes import ROOT,SOURCE,ROWS

SQL=f'''WITH raw AS (SELECT * FROM {SOURCE}),
numbered AS (SELECT *,CAST(ROW_NUMBER() OVER(PARTITION BY eid ORDER BY tick,point) AS BIGINT) ordinal FROM raw),
frame_rows AS (SELECT a.point,a.eid,a.ordinal,b.ordinal frame_row,b.value,b.y,b.weight FROM numbered a JOIN numbered b ON a.eid=b.eid AND b.ordinal BETWEEN a.ordinal-3 AND a.ordinal),
summary AS (SELECT point,eid,ordinal,COUNT(value) n,AVG(value) mean_x,AVG(CASE WHEN value IS NOT NULL THEN y ELSE NULL END) mean_y,
SUM(value*value) sum2,SUM(value*weight) wsum,SUM(CASE WHEN value IS NOT NULL THEN weight ELSE 0 END) weight_sum,
MIN(value) minimum,MAX(value) maximum,MAX(y) max_y,MIN(y) min_y,
MIN(CASE WHEN value IS NOT NULL THEN frame_row ELSE NULL END) first_member,MAX(CASE WHEN value IS NOT NULL THEN frame_row ELSE NULL END) last_member,
SUM(CASE WHEN value=0 THEN 1 ELSE 0 END) zeros,SUM(CASE WHEN value<0 THEN 1 ELSE 0 END) negatives,
SUM(CASE WHEN value IS NOT NULL AND value<>0 THEN LN(ABS(value)) ELSE 0 END) product_log FROM frame_rows GROUP BY point,eid,ordinal),
moments AS (SELECT f.point,f.eid,SUM(POWER(f.value-s.mean_x,2)) c2,SUM(POWER(f.value-s.mean_x,3)) c3,SUM(POWER(f.value-s.mean_x,4)) c4,
SUM((f.value-s.mean_x)*(f.y-s.mean_y)) cxy,SUM(CASE WHEN f.value IS NOT NULL THEN POWER(f.y-s.mean_y,2) ELSE NULL END) cy2,
MIN(CASE WHEN f.value=s.minimum THEN f.frame_row ELSE NULL END) min_member,MAX(CASE WHEN f.value=s.minimum THEN f.frame_row ELSE NULL END) min_last_member,
MIN(CASE WHEN f.value=s.maximum THEN f.frame_row ELSE NULL END) max_member,MAX(CASE WHEN f.value=s.maximum THEN f.frame_row ELSE NULL END) max_last_member,
MIN(CASE WHEN f.y=s.max_y THEN f.frame_row ELSE NULL END) max_y_member,MIN(CASE WHEN f.y=s.min_y THEN f.frame_row ELSE NULL END) min_y_member
FROM frame_rows f JOIN summary s ON f.point=s.point AND f.eid=s.eid GROUP BY f.point,f.eid),
result AS (SELECT s.*,m.c2,m.c3,m.c4,m.cxy,m.cy2,m.min_member,m.min_last_member,m.max_member,m.max_last_member,m.max_y_member,m.min_y_member,
f.value first_nonnull,l.value last_nonnull,ma.value at_max_location,mi.value at_min_location FROM summary s JOIN moments m ON s.eid=m.eid AND s.point=m.point
LEFT JOIN numbered f ON f.eid=s.eid AND f.ordinal=s.first_member LEFT JOIN numbered l ON l.eid=s.eid AND l.ordinal=s.last_member
LEFT JOIN numbered ma ON ma.eid=s.eid AND ma.ordinal=m.max_y_member LEFT JOIN numbered mi ON mi.eid=s.eid AND mi.ordinal=m.min_y_member)
SELECT point,eid,sum2,
min_member-GREATEST(1,ordinal-3) imin,min_last_member-GREATEST(1,ordinal-3) iminLast,
max_member-GREATEST(1,ordinal-3) imax,max_last_member-GREATEST(1,ordinal-3) imaxLast,
CASE WHEN n>0 AND c2>1e-12 THEN c3/n/POWER(c2/n,CAST(1.5 AS DOUBLE)) ELSE NULL END skew,
CASE WHEN n>0 AND c2>1e-12 THEN c4/n/POWER(c2/n,2) ELSE NULL END kurtosis,
first_nonnull firstNot,last_nonnull lastNot,
CASE WHEN n=0 THEN NULL WHEN zeros>0 THEN 0 ELSE EXP(product_log)*CASE WHEN MOD(negatives,2)=0 THEN 1 ELSE -1 END END prod,
wsum/NULLIF(weight_sum,0) wavg,wsum,
CASE WHEN c2>1e-12 AND cy2>1e-12 THEN cxy/SQRT(c2*cy2) ELSE NULL END corr,
CASE WHEN n>1 THEN cxy/(n-1) ELSE NULL END covar,
CASE WHEN c2>1e-12 THEN cxy/c2 ELSE NULL END beta,
at_max_location atImax,at_min_location atImin FROM result ORDER BY eid,point'''

def expected():
 rows=[]
 for eid in sorted({r[1] for r in ROWS}):
  data=sorted([r for r in ROWS if r[1]==eid],key=lambda r:(r[2],r[0]))
  for j,current in enumerate(data):
   frame=data[max(0,j-3):j+1];x=np.array([np.nan if r[3] is None else r[3] for r in frame]);y=np.array([r[4] for r in frame]);w=np.array([r[5] for r in frame]);valid=~np.isnan(x);v=x[valid];vy=y[valid];vw=w[valid];n=len(v);row=dict(point=current[0],eid=eid,sum2=float(np.sum(v*v)) if n else np.nan)
   if n:
    mn=np.flatnonzero(x==np.nanmin(x));mx=np.flatnonzero(x==np.nanmax(x));row.update(imin=int(mn[0]),iminLast=int(mn[-1]),imax=int(mx[0]),imaxLast=int(mx[-1]),firstNot=float(v[0]),lastNot=float(v[-1]),prod=float(np.prod(v)),wavg=float(np.sum(v*vw)/np.sum(vw)),wsum=float(np.sum(v*vw)))
    c2=float(np.sum((v-v.mean())**2));cy2=float(np.sum((vy-vy.mean())**2));cross=float(np.sum((v-v.mean())*(vy-vy.mean())))
    with warnings.catch_warnings():
     warnings.simplefilter('ignore');row.update(skew=float(stats.skew(v,bias=True)) if c2>1e-12 else np.nan,kurtosis=float(stats.kurtosis(v,bias=True,fisher=False)) if c2>1e-12 else np.nan)
    row.update(corr=cross/np.sqrt(c2*cy2) if c2>1e-12 and cy2>1e-12 else np.nan,covar=cross/(n-1) if n>1 else np.nan,beta=cross/c2 if c2>1e-12 else np.nan)
   else:
    for key in ['imin','iminLast','imax','imaxLast','firstNot','lastNot','prod','wavg','wsum','skew','kurtosis','corr','covar','beta']:row[key]=np.nan
   row['atImax']=float(x[np.argmax(y)]);row['atImin']=float(x[np.argmin(y)]);rows.append(row)
 return pd.DataFrame(rows)
def main():
 c=connect()
 try:a=read(c,SQL)
 finally:c.close()
 g=expected()[list(a)];np.testing.assert_allclose(a.to_numpy(float),g.to_numpy(float),rtol=1e-7,atol=1e-7,equal_nan=True)
 (ROOT/'results/rewrites-all17.json').write_text(json.dumps(dict(status='pass',columns=list(a),rows=len(a),expected=plain(g.to_numpy(float)),actual=plain(a.to_numpy(float)),sql=SQL,scope='Default mathematical profiles on ten rows, ROWS width four, NULL skipping, earliest tie, biased skew and Pearson kurtosis, sample covariance. Original-fixture NumPy/SciPy independently validates every value; no live DolphinDB execution or all-parameter equivalence/performance claim.'),indent=2,allow_nan=False));(ROOT/'results/rewrites-all17.sql').write_text(SQL+';\n');print('All 17 missing dedicated SQL primitives: MO combinations match independent math for the declared profile.',flush=True)
if __name__=='__main__':main()
