"""Isolated complex full-workflow timing, excluding reference checks/publication."""
import collections,concurrent.futures,json,time
import numpy as np,pandas as pd
from sqlalchemy import text
from data import ROOT,tables,local_oracle,connect,engine
from graphs import QUESTIONS,query
from models import calculate
from pandas_graphs import build
from common import compare,equal
from audit import snapshot

def main():
    source=snapshot('performance');oracle=local_oracle(tables());shapes=[(f,i) for f in [0,3,7,11,19] for i in [49,449]]
    references={};facts={}
    for f,i in shapes:
        key=(QUESTIONS[f][0],i)
        if key not in facts:facts[key]=oracle.execute(query(key[0],i)).fetchdf()
        references[(f,i)]=calculate(f,facts[key],i)
    groups=[];records=[]
    for client in ['pymysql_numpy','pandas_sqlalchemy']:
        for trial in range(3):
            for concurrency in [[1,4,2,8],[8,2,4,1],[2,8,1,4]][trial]:
                batch=shapes*2;start=time.perf_counter()
                def job(pair):
                    f,i=pair;domain=QUESTIONS[f][0];c=connect();eng=engine() if client.startswith('pandas') else None;sql=query(domain,i);t=time.perf_counter()
                    if eng:
                        with eng.connect() as con:a=pd.read_sql(text(sql),con,coerce_float=False)
                        native=build(source,domain,i,a.columns);am=calculate(f,native,i,'pandas')
                    else:
                        with c.cursor() as q:q.execute(sql);a=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
                        am=calculate(f,a,i)
                    elapsed=(time.perf_counter()-t)*1000
                    compare(facts[(domain,i)],a)
                    if eng:compare(a,native)
                    assert equal(references[pair],am) and all(am['checks'].values())
                    c.close()
                    if eng:eng.dispose()
                    return {'client':client,'trial':trial,'concurrency':concurrency,'family':f,'parameter':i,'ms':elapsed,'status':'pass'}
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:result=list(pool.map(job,batch))
                seconds=time.perf_counter()-start;groups.append({'client':client,'trial':trial,'concurrency':concurrency,'workflows':len(batch),'seconds':seconds});records.extend(result)
                print(client,concurrency,trial,'pass',round(seconds,3),flush=True)
    summary=[]
    for client in ['pymysql_numpy','pandas_sqlalchemy']:
        for concurrency in [1,2,4,8]:
            lat=[r['ms'] for r in records if r['client']==client and r['concurrency']==concurrency];elapsed=sum(r['seconds'] for r in groups if r['client']==client and r['concurrency']==concurrency)
            summary.append({'client':client,'concurrency':concurrency,'workflows':len(lat),'workflows_per_second':len(lat)/elapsed,'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,[*np.quantile(lat,[.5,.95,.99]),max(lat)])))})
    (ROOT/'performance.json').write_text(json.dumps({'total':len(records),'counts':{'pass':len(records)},'groups':summary,'trials':groups,'records':records,'scope':'19-source-table SQL reads + DataFrame + science; pandas also includes its independent source-graph reconstruction from a verified shared source snapshot. Connection initialization, source snapshot acquisition, reference checking and transaction publication excluded from per-case latency. Throughput wall-time includes scheduling/connection/check overhead.'},indent=2));oracle.close()
if __name__=='__main__':main()
