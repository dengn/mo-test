"""Positive/negative trajectory speed controls using the held-out antimeridian cohort."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import ROOT,tables,connect,read,compare,plain,values
from native import Native
from analytics import analyze
from scenarios import params,sql_for
out=ROOT/'results/speed-controls';out.mkdir(exist_ok=False);data=tables();native=Native(data);c=connect();start=time.time();counts=dict(cases=0,passed=0,failed=0,positive_detection_cases=0,zero_detection_cases=0)
with (out/'cases.jsonl').open('w') as f:
 for i in range(100):
  p=params(8,4,i);sql=sql_for(8,4,i).replace(f'g.uid BETWEEN {p["lo"]} AND {p["hi"]}','g.uid BETWEEN 31 AND 32');p.update(lo=31,hi=32);r=dict(case_id=i,parameters=p,sql=sql,status='pass')
  try:
   g=native._expected(8,4,p);a=read(c,sql);compare(g,a,1e-7);e=analyze(8,4,i,g,True,data);actual=analyze(8,4,i,a,False,data);compare(e,actual,1e-6);positive=bool(e.metric_a.sum()>0);counts['positive_detection_cases']+=positive;counts['zero_detection_cases']+=not positive;r.update(positive_detection=positive,columns=list(e),expected=values(e),actual=values(actual))
  except Exception as ex:r.update(status='fail',error=str(ex))
  counts['cases']+=1;counts['passed']+=r['status']=='pass';counts['failed']+=r['status']!='pass';f.write(json.dumps(plain(r),separators=(',',':'))+'\n')
c.close();assert counts['positive_detection_cases']>0 and counts['zero_detection_cases']>0;counts.update(elapsed_seconds=time.time()-start,scope='100 supplemental speed threshold controls on uid31/32 antimeridian trajectories. Ordinary main template4 cohorts have low speeds and mainly exercise normal classifications; these explicitly include positive and negative detections. Not added to canonical count.');(out/'summary.json').write_text(json.dumps(counts,indent=2));print(counts)
