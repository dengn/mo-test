"""10000 complete 19/20-table business workflows with native pandas and NumPy."""
import argparse,collections,concurrent.futures,hashlib,json,threading,time,traceback
from pathlib import Path
import numpy as np,pandas as pd,psutil
from sqlalchemy import text
from data import ROOT,DB,tables,local_oracle,connect,engine
from audit import snapshot
from graphs import QUESTIONS,query,params
from models import calculate
from pandas_graphs import build
from common import equal,compare,receipt

def monitor(stop,out):
    pid=int(Path('/workspace/mo-ds-lab/server.pid').read_text());proc=psutil.Process(pid);c=connect()
    with (out/'health.jsonl').open('w') as file:
        while not stop.is_set():
            r={'time':time.time(),'pid':pid}
            try:c.ping(reconnect=False);r.update(status='ok',rss_mib=proc.memory_info().rss/2**20)
            except Exception as exc:r.update(status='error',error=str(exc))
            file.write(json.dumps(r)+'\n');file.flush();stop.wait(5)
    c.close()

def publish(c,w,case,am,em):
    table=f'cross_decisions_{w}';steps=[]
    def execute(sql):
        t=time.perf_counter()
        with c.cursor() as q:q.execute(sql);rows=q.fetchall()
        steps.append({'sql':sql,'ms':(time.perf_counter()-t)*1000});return rows
    execute('BEGIN');records=[(case,*r) for r in am['decisions']]
    with c.cursor() as q:q.executemany(f'INSERT INTO {table} VALUES(%s,%s,%s,%s)',records)
    steps.append({'sql':f'INSERT INTO {table} VALUES(bound actual decisions)','rows':len(records)})
    read=f'SELECT entity,allocation,benefit FROM {table} WHERE case_id={case} ORDER BY entity'
    expected=sorted(em['decisions']);assert equal(expected,execute(read)),'decision readback'
    aggregate=f'SELECT COUNT(*),SUM(allocation),SUM(benefit) FROM {table} WHERE case_id={case}'
    earr=np.asarray(expected);assert equal([[len(earr),earr[:,1].sum(),earr[:,2].sum()]],execute(aggregate)),'decision aggregate'
    commit=case%2==0;execute('COMMIT' if commit else 'ROLLBACK');assert equal(expected if commit else [],execute(read)),'transaction visibility'
    execute(f'DELETE FROM {table} WHERE case_id={case}');return steps

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',type=int,default=0);ap.add_argument('--workers',type=int,default=6);args=ap.parse_args()
    source=snapshot('initial');out=ROOT/'results'/('pilot' if args.pilot else 'canonical');out.mkdir(parents=True,exist_ok=True)
    indices=list(map(int,np.linspace(0,499,args.pilot,dtype=int))) if args.pilot else list(range(500));target=len(indices)*20;started=time.time();c=connect()
    for w in range(args.workers):
        with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS cross_decisions_{w}(case_id INT,entity DOUBLE,allocation DOUBLE,benefit DOUBLE)');q.execute(f'SELECT COUNT(*) FROM cross_decisions_{w}');assert q.fetchone()[0]==0
    c.close();stop=threading.Event();health=threading.Thread(target=monitor,args=(stop,out));health.start();counts=collections.Counter();lock=threading.Lock()
    log=Path('/workspace/mo-ds-lab/server.log');offset=log.stat().st_size
    def worker(w,indices):
        oracle=local_oracle(tables());c=connect();eng=engine()
        with (out/f'cases-{w}.jsonl').open('w') as file:
            for i in indices:
                expected={d:oracle.execute(query(d,i)).fetchdf() for d in ['customer','product']}
                native={d:build(source,d,i,expected[d].columns) for d in ['customer','product']} if i%2 else {}
                for f,(domain,key,question) in enumerate(QUESTIONS):
                    case=f*500+i;t=time.perf_counter();r={'case_id':case,'requirement':key,'question':question,'parameters':params(i),'parameter':i,'client':'pandas_sqlalchemy' if i%2 else 'pymysql_numpy','sql':query(domain,i)};state='extract'
                    try:
                        tq=time.perf_counter()
                        if i%2:
                            with eng.connect() as con:a=pd.read_sql(text(r['sql']),con,coerce_float=False)
                        else:
                            with c.cursor() as q:q.execute(r['sql']);a=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
                        r['extract_ms']=(time.perf_counter()-tq)*1000;compare(expected[domain],a);r['expected_facts']=receipt(expected[domain]);r['actual_facts']=receipt(a)
                        if i%2:compare(expected[domain],native[domain]);compare(a,native[domain]);r['native_pandas_facts']=receipt(native[domain])
                        state='analysis';ta=time.perf_counter();em=calculate(f,expected[domain],i);am=calculate(f,native[domain] if i%2 else a,i,'pandas' if i%2 else 'numpy')
                        r.update(expected_analysis=em,actual_analysis=am,paired_analysis_ms=(time.perf_counter()-ta)*1000)
                        assert all(em['checks'].values()),('reference constraints',em['checks']);assert all(am['checks'].values()),('actual constraints',am['checks']);assert equal(em,am),'scientific model mismatch'
                        state='publication';r['publication']=publish(c,w,case,am,em);r['status']='pass'
                    except Exception as exc:
                        r.update(status='sql_error' if state=='extract' and not isinstance(exc,AssertionError) else state+'_error',error=str(exc),traceback=traceback.format_exc())
                        if state=='extract' and 'a' in locals():r['failed_facts']=a.to_numpy(float).tolist()
                        try:
                            c.rollback()
                            with c.cursor() as q:q.execute(f'DELETE FROM cross_decisions_{w} WHERE case_id=%s',(case,))
                        except Exception:pass
                    r['ms']=(time.perf_counter()-t)*1000;file.write(json.dumps(r,allow_nan=False)+'\n');file.flush()
                    with lock:
                        counts[r['status']]+=1;n=sum(counts.values())
                        if n%100==0:print(json.dumps({'completed':n,'target':target,'counts':dict(counts),'seconds':round(time.time()-started,1)}),flush=True)
        c.close();eng.dispose();oracle.close()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(lambda z:worker(*z),[(w,indices[w::args.workers]) for w in range(args.workers)]))
    finally:stop.set();health.join()
    meta={'cases':len(indices)*20,'counts':dict(counts),'seconds':time.time()-started,'workers':args.workers,'started_at':started,'ended_at':time.time(),'log_start_offset':offset,'log_end_offset':log.stat().st_size,'database':DB}
    (out/'meta.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True)
    assert sum(counts.values())==len(indices)*20
if __name__=='__main__':main()
