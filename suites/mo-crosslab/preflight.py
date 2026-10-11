import json,time,traceback
import pandas as pd
from data import ROOT,tables,setup,local_oracle,connect
from graphs import QUESTIONS,query
from models import calculate
from common import compare,equal

def main():
    data=tables();setup(data);o=local_oracle(data);c=connect();rows=[]
    for i in [0,249,499]:
        for domain in ['customer','product']:
            sql=query(domain,i);t=time.perf_counter();e=o.execute(sql).fetchdf()
            try:
                with c.cursor() as q:q.execute(sql);a=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
                compare(e,a);print(domain,i,len(a),round(time.perf_counter()-t,3),flush=True)
                for f,(d,key,_) in enumerate(QUESTIONS):
                    if d!=domain:continue
                    em=calculate(f,e,i);am=calculate(f,a,i,'pandas')
                    assert all(em['checks'].values()),('reference checks',key,em['checks'])
                    assert all(am['checks'].values()),('actual checks',key,am['checks'])
                    assert equal(em,am),('model mismatch',key)
                    rows.append(dict(case_id=f*500+i,mission=key,status='pass'));print(' model',key,'pass',flush=True)
            except Exception as exc:
                rows.append(dict(domain=domain,parameter=i,status='error',error=str(exc),traceback=traceback.format_exc()));print(traceback.format_exc(),flush=True)
    (ROOT/'preflight.json').write_text(json.dumps(rows,indent=2));c.close();o.close()
    assert len(rows)==60 and all(r['status']=='pass' for r in rows)
if __name__=='__main__':main()
