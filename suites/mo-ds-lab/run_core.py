"""98,000 independently executed SQL cases, with pandas/NumPy result oracles."""
import argparse
import concurrent.futures
import hashlib
import importlib.metadata as metadata
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
from sqlalchemy import text
from common import ROOT, SEED, connection, dataset, engine, equal, plain, setup

# Ordered: case IDs and SQL are stable across reruns.
SPECS=[
 ('count','COUNT(*)'),('nullable_count','COUNT(nx)'),('sum','SUM(x)'),
 ('mean','AVG(x)'),('min','MIN(x)'),('max','MAX(x)'),
 ('variance_pop','VAR_POP(x)'),('variance_sample','VAR_SAMP(x)'),
 ('stddev_pop','STDDEV_POP(x)'),('stddev_sample','STDDEV_SAMP(x)'),
 ('squared_norm','SUM(x*x)'),('dot','SUM(x*y)'),
 ('covariance','AVG(x*y)-AVG(x)*AVG(y)'),
 ('correlation','(AVG(x*y)-AVG(x)*AVG(y))/SQRT((AVG(x*x)-AVG(x)*AVG(x))*(AVG(y*y)-AVG(y)*AVG(y)))'),
 ('abs','AVG(ABS(x))'),('ceil','AVG(CEIL(x))'),('floor','AVG(FLOOR(x))'),
 ('sqrt','AVG(SQRT(ABS(x)))'),('log','AVG(LN(ABS(x)+1))'),
 ('exp','AVG(EXP(x/100))'),('cube','AVG(POWER(x,3))'),
 ('sin','AVG(SIN(x))'),('cos','AVG(COS(x))'),('tanh','AVG(TANH(x/100))'),
 ('log10','AVG(LOG10(ABS(x)+1))'),('modulo','SUM(MOD(k,7))'),
 ('null_count','SUM(CASE WHEN nx IS NULL THEN 1 ELSE 0 END)'),
 ('imputation','SUM(COALESCE(nx,0))'),
 ('winsorization','AVG(CASE WHEN x < -50 THEN -50 WHEN x>50 THEN 50 ELSE x END)'),
 ('positive_count','SUM(CASE WHEN x>0 THEN 1 ELSE 0 END)'),
 ('weighted_mean','SUM(x*(ABS(y)+1))/SUM(ABS(y)+1)'),
 ('distinct','COUNT(DISTINCT k)'),('group_cardinality','COUNT(DISTINCT g)'),
 ('group_mean_sum','SELECT SUM(v) FROM (SELECT AVG(x) v FROM ds WHERE {where} GROUP BY g) a'),
 ('top5','SELECT SUM(x) FROM (SELECT x FROM ds WHERE {where} ORDER BY x DESC,id LIMIT 5) a'),
 ('median','SELECT AVG(x) FROM (SELECT x,ROW_NUMBER() OVER(ORDER BY x,id) rn,COUNT(*) OVER() n FROM ds WHERE {where}) a WHERE rn IN(FLOOR((n+1)/2),FLOOR((n+2)/2))'),
 ('cumulative_sum','SELECT v FROM (SELECT id,SUM(x) OVER(ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) v FROM ds WHERE {where}) a ORDER BY id DESC LIMIT 1'),
 ('moving_mean','SELECT SUM(v) FROM (SELECT AVG(x) OVER(ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) v FROM ds WHERE {where}) a'),
 ('lag_difference','SELECT SUM(x-v) FROM (SELECT x,LAG(x) OVER(ORDER BY id) v FROM ds WHERE {where}) a'),
 ('lead_difference','SELECT SUM(v-x) FROM (SELECT x,LEAD(x) OVER(ORDER BY id) v FROM ds WHERE {where}) a'),
 ('rank','SELECT SUM(v) FROM (SELECT RANK() OVER(ORDER BY k) v FROM ds WHERE {where}) a'),
 ('dense_rank','SELECT SUM(v) FROM (SELECT DENSE_RANK() OVER(ORDER BY k) v FROM ds WHERE {where}) a'),
 ('ntile','SELECT SUM(v) FROM (SELECT NTILE(4) OVER(ORDER BY id) v FROM ds WHERE {where}) a'),
 ('row_number','SELECT SUM(v) FROM (SELECT ROW_NUMBER() OVER(ORDER BY id) v FROM ds WHERE {where}) a'),
 ('unicode_length','SUM(CHAR_LENGTH(txt))'),('byte_length','SUM(LENGTH(txt))'),
 ('day_feature','SUM(DAY(ts))'),('hour_feature','SUM(HOUR(ts))'),
 ('json_feature',"SUM(CAST(JSON_EXTRACT(js,'$.v') AS SIGNED))"),
]
assert len(SPECS)==49

def parameters(i):
    lo=(i*7)%4096; hi=lo+32+(i*13)%1024
    # Every tenth parameter deliberately gives an empty result.
    g=99 if i%10==0 else i%17
    return lo,hi,g

def oracle(name,a,mode):
    n=len(a)
    x,y,k,nx = (a[c] if mode=='pandas' else a[c].to_numpy() for c in ['x','y','k','nx'])
    if name=='count': return n
    if name=='nullable_count': return int(a.nx.notna().sum()) if mode=='pandas' else int(np.isfinite(nx).sum())
    if name in ('distinct','group_cardinality'):
        z=a.k if name=='distinct' else a.g
        return z.nunique() if mode=='pandas' else len(np.unique(z))
    if n==0: return None
    agg=lambda z,op: getattr(z,op)() if mode=='pandas' else getattr(np,op)(z)
    if name in ('sum','mean','min','max'): return plain(agg(x,name))
    if name.startswith('variance') or name.startswith('stddev'):
        ddof=1 if name.endswith('sample') else 0
        if n<=ddof: return None
        return plain(x.var(ddof=ddof) if name.startswith('variance') else x.std(ddof=ddof))
    ops={
      'squared_norm':lambda:agg(x*x,'sum'), 'dot':lambda:agg(x*y,'sum'),
      'covariance':lambda:((x-x.mean())*(y-y.mean())).mean(),
      'correlation':lambda:a.x.corr(a.y) if mode=='pandas' else np.corrcoef(x,y)[0,1],
      'abs':lambda:agg(np.abs(x),'mean'),'ceil':lambda:agg(np.ceil(x),'mean'),
      'floor':lambda:agg(np.floor(x),'mean'),'sqrt':lambda:agg(np.sqrt(np.abs(x)),'mean'),
      'log':lambda:agg(np.log1p(np.abs(x)),'mean'),'exp':lambda:agg(np.exp(x/100),'mean'),
      'cube':lambda:agg(x**3,'mean'),'sin':lambda:agg(np.sin(x),'mean'),
      'cos':lambda:agg(np.cos(x),'mean'),'tanh':lambda:agg(np.tanh(x/100),'mean'),
      'log10':lambda:agg(np.log10(np.abs(x)+1),'mean'),
      'modulo':lambda:agg(k-np.trunc(k/7)*7,'sum'),
      'null_count':lambda:int(a.nx.isna().sum()) if mode=='pandas' else int(np.isnan(nx).sum()),
      'imputation':lambda:a.nx.fillna(0).sum() if mode=='pandas' else np.nansum(nx),
      'winsorization':lambda:agg(np.clip(x,-50,50),'mean'),
      'positive_count':lambda:agg((x>0).astype(int),'sum'),
      'weighted_mean':lambda:np.average(x,weights=np.abs(y)+1),
      'group_mean_sum':lambda:a.groupby('g').x.mean().sum() if mode=='pandas' else sum(x[a.g.to_numpy()==g].mean() for g in np.unique(a.g)),
      'top5':lambda:a.x.nlargest(5).sum() if mode=='pandas' else np.sort(x)[-5:].sum(),
      'median':lambda:a.x.median() if mode=='pandas' else np.median(x),
      'cumulative_sum':lambda:a.x.cumsum().iloc[-1] if mode=='pandas' else np.cumsum(x)[-1],
      'moving_mean':lambda:a.x.rolling(3,min_periods=1).mean().sum() if mode=='pandas' else sum(x[max(0,j-2):j+1].mean() for j in range(n)),
      'lag_difference':lambda:a.x.diff().sum() if mode=='pandas' else np.diff(x).sum(),
      'lead_difference':lambda:(a.x.shift(-1)-a.x).sum() if mode=='pandas' else np.diff(x).sum(),
      'rank':lambda:a.k.rank(method='min').sum() if mode=='pandas' else sum(np.searchsorted(np.sort(k),v)+1 for v in k),
      'dense_rank':lambda:a.k.rank(method='dense').sum() if mode=='pandas' else sum(np.searchsorted(np.unique(k),v)+1 for v in k),
      'ntile':lambda:sum((j+1)*size for j,size in enumerate([n//4+(j<n%4) for j in range(4)])),
      'row_number':lambda:n*(n+1)//2,
      'unicode_length':lambda:a.txt.str.len().sum() if mode=='pandas' else sum(map(len,a.txt)),
      'byte_length':lambda:sum(len(t.encode('utf8')) for t in a.txt),
      'day_feature':lambda:a.ts.dt.day.sum(), 'hour_feature':lambda:a.ts.dt.hour.sum(),
      'json_feature':lambda:sum(json.loads(s)['v'] for s in a.js),
    }
    return plain(ops[name]())

def sql_for(name,expr,i):
    lo,hi,g=parameters(i)
    where=f'id>={lo} AND id<{hi} AND g={g}'
    return expr.format(where=where) if expr.startswith('SELECT ') else f'SELECT {expr} AS v FROM ds WHERE {where}'

def monitor(stop,path):
    pid=int((ROOT/'server.pid').read_text()); process=psutil.Process(pid)
    c=None
    with path.open('w') as f:
        while not stop.is_set():
            record={'time':time.time(),'pid':pid}
            try:
                record.update(rss_bytes=process.memory_info().rss,
                  cpu_seconds=sum(process.cpu_times()[:2]), alive=process.is_running())
                if c is None: c=connection()
                start=time.perf_counter()
                with c.cursor() as q: q.execute('SELECT 1'); record['ping']=q.fetchone()[0]
                record['ping_ms']=(time.perf_counter()-start)*1000
            except Exception as e:
                record['error']=str(e); c=None
            record['memory_events']=Path('/sys/fs/cgroup/memory.events').read_text()
            f.write(json.dumps(record)+'\n'); f.flush()
            stop.wait(5)
    if c: c.close()

def worker(worker_id,items,out,refs):
    c=connection(); e=engine()
    with (out/f'core-{worker_id:02d}.jsonl').open('w') as f:
        for index in items:
            mode='pandas' if index<49000 else 'numpy'
            case=index%49000; spec_i,i=divmod(case,1000)
            name,expr=SPECS[spec_i]; sql=sql_for(name,expr,i)
            r={'case_id':index,'tool':mode,'family':name,'parameter':i,
                'sql':sql,'expected':refs[(mode,spec_i,i)]}
            start=time.perf_counter()
            try:
                if mode=='pandas':
                    with e.connect() as ec: df=pd.read_sql_query(text(sql),ec)
                    actual=df.iat[0,0] if len(df) else None
                else:
                    with c.cursor() as q: q.execute(sql); row=q.fetchone()
                    actual=row[0] if row else None
                r['query_ms']=(time.perf_counter()-start)*1000
                r['actual']=plain(float(actual) if actual is not None else None)
                r['status']='pass' if equal(r['actual'],r['expected']) else 'mismatch'
            except Exception as exc:
                r.update(status='sql_or_client_error',error=str(exc),error_type=type(exc).__name__,query_ms=(time.perf_counter()-start)*1000)
                # Never retry this case or turn a recovered connection into a pass.
                try: c.close()
                except Exception: pass
                try: c=connection()
                except Exception: pass
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
            if case%100==0: f.flush()
    c.close(); e.dispose()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--workers',type=int,default=8)
    p.add_argument('--limit',type=int,default=98000); p.add_argument('--out',default='results/core')
    args=p.parse_args(); out=ROOT/args.out; out.mkdir(parents=True,exist_ok=True)
    version=setup(); d=dataset(); refs={}
    started=time.time()
    print('Building independent oracles...',flush=True)
    for i in range(1000):
        lo,hi,g=parameters(i); a=d[(d.id>=lo)&(d.id<hi)&(d.g==g)]
        for j,(name,_) in enumerate(SPECS):
            for mode in ('pandas','numpy'): refs[(mode,j,i)]=oracle(name,a,mode)
    for j,_ in enumerate(SPECS):
        for i in range(1000):
            assert equal(refs[('pandas',j,i)],refs[('numpy',j,i)]), (j,i)
    oracle_time=time.time()-started
    indices=np.arange(98000); np.random.default_rng(SEED).shuffle(indices)
    if args.limit<98000: indices=indices[:args.limit]
    meta={'seed':SEED,'mo_version':version,'workers':args.workers,'planned':len(indices),
        'oracle_seconds':oracle_time,'families':len(SPECS),'parameters_per_family':1000,
        'binary_sha256':hashlib.sha256(Path('/workspace/matrixone/mo-service').read_bytes()).hexdigest(),
        'versions':{x:metadata.version(x) for x in ('pandas','numpy','sqlalchemy','pymysql')},
        'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
        'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
        'timing_scope':'client SQL execution plus result fetch (pandas includes DataFrame conversion); oracle generation excluded'}
    (out/'meta.json').write_text(json.dumps(meta,indent=2))
    stop=threading.Event(); thread=threading.Thread(target=monitor,args=(stop,out/'health.jsonl')); thread.start()
    start=time.time(); print(f'Executing {len(indices)} cases with {args.workers} connections...',flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(worker,w,indices[w::args.workers].tolist(),out,refs) for w in range(args.workers)]
            for f in futures: f.result()
    finally: stop.set(); thread.join()
    meta.update(execution_seconds=time.time()-start,completed_at=time.time())
    (out/'meta.json').write_text(json.dumps(meta,indent=2)); print(json.dumps(meta),flush=True)

if __name__=='__main__': main()
