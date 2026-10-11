"""Million-row benchmarks, type round trips, vector probes and a short write soak.

These checks supplement the canonical 100,000 cases and are counted separately.
"""
import concurrent.futures
import argparse
from decimal import Decimal
import json
import threading
import time

import numpy as np
import pandas as pd
from sqlalchemy import DECIMAL, text
from common import ROOT,connection,dataset,engine,equal,plain
from run_core import monitor

OUT=ROOT/'results/supplemental'

def type_checks():
    records=[]; c=connection(); e=engine()
    def save(name,fn):
        try: detail=fn(); records.append({'name':name,'status':'pass','detail':detail})
        except Exception as ex: records.append({'name':name,'status':'failure','error':str(ex)})
    def full_read():
        df=pd.read_sql_query('SELECT * FROM ds ORDER BY id',e)
        ref=dataset()
        assert len(df)==len(ref)==8192
        for col in ('id','g','k','txt'):
            assert df[col].tolist()==ref[col].tolist(),col
        for col in ('x','y','nx'):
            np.testing.assert_allclose(df[col],ref[col],rtol=1e-12,atol=1e-12,equal_nan=True)
        assert pd.to_datetime(df.ts).equals(ref.ts)
        assert [json.loads(s) for s in df.js]==[json.loads(s) for s in ref.js]
        return {'rows':8192,'types':{col:str(t) for col,t in df.dtypes.items()}}
    save('pandas_full_dataframe_roundtrip',full_read)
    def decimal_check():
        with c.cursor() as q:
            q.execute('CREATE TABLE IF NOT EXISTS pandas_decimal (id INT,v DECIMAL(38,18))')
            q.execute('TRUNCATE TABLE pandas_decimal')
        values=[Decimal('12345678901234567890.123456789012345678'),
                Decimal('-0.000000000000000001'),Decimal('0'),None]
        df=pd.DataFrame({'id':range(4),'v':values})
        df.to_sql('pandas_decimal',e,if_exists='append',index=False,method='multi',dtype={'v':DECIMAL(38,18)})
        back=pd.read_sql_query('SELECT v FROM pandas_decimal ORDER BY id',e,coerce_float=False)
        assert back.v.tolist()==values,back.v.tolist()
        return {'rows':4,'coerce_float':False}
    save('pandas_decimal38_exact_roundtrip',decimal_check)
    def boundary_check():
        with c.cursor() as q:
            q.execute('CREATE TABLE IF NOT EXISTS boundary_types(id INT,i BIGINT,u BIGINT UNSIGNED,t VARCHAR(100),b VARBINARY(100),ts DATETIME)')
            q.execute('TRUNCATE TABLE boundary_types')
            rows=[(1,-2**63,2**64-1,'数据🚀\x00',b'\x00\xff\x80','2024-02-29 23:59:59'),
                  (2,2**63-1,0,'',b'','1900-01-01 00:00:00'),(3,None,None,None,None,None)]
            q.executemany('INSERT INTO boundary_types VALUES(%s,%s,%s,%s,%s,%s)',rows)
            q.execute('SELECT id,i,u,t,b,ts FROM boundary_types ORDER BY id'); got=q.fetchall()
        for a,b in zip(rows,got):
            assert a[:5]==b[:5],(a,b)
            assert a[5]==(str(b[5]) if b[5] else None)
        return {'rows':3,'covers':['int64_min','int64_max','uint64_max','unicode','nul_byte','binary','leap_date','NULL']}
    save('integer_unicode_binary_datetime_boundaries',boundary_check)
    # Exercise actual typed MO vectors; errors remain visible as incompatibilities.
    rng=np.random.default_rng(20261011)
    a=rng.normal(size=(32,8)); b=rng.normal(size=(32,8))
    with c.cursor() as q:
        q.execute('CREATE TABLE IF NOT EXISTS vector_probe(id INT,a VECF64(8),b VECF64(8))')
        q.execute('TRUNCATE TABLE vector_probe')
        q.executemany('INSERT INTO vector_probe VALUES(%s,%s,%s)',[(i,json.dumps(x.tolist()),json.dumps(y.tolist())) for i,(x,y) in enumerate(zip(a,b))])
    specs={'l2_distance':('l2_distance(a,b)',np.linalg.norm(a-b,axis=1)),
           'cosine_distance':('cosine_distance(a,b)',1-np.sum(a*b,axis=1)/(np.linalg.norm(a,axis=1)*np.linalg.norm(b,axis=1))),
           'inner_product':('inner_product(a,b)',np.sum(a*b,axis=1))}
    for name,(expr,expected) in specs.items():
        def check(expr=expr,expected=expected):
            with c.cursor() as q: q.execute(f'SELECT {expr} FROM vector_probe ORDER BY id'); vals=[r[0] for r in q.fetchall()]
            np.testing.assert_allclose(vals,expected,rtol=1e-7,atol=1e-7)
            return {'rows':32,'dimensions':8}
        save('numpy_vector_'+name,check)
    with c.cursor() as q:
        q.execute('SELECT id,inner_product(a,b) FROM vector_probe ORDER BY id')
        vec_rows=q.fetchall()
    dot=np.sum(a*b,axis=1); actual=np.array([r[1] for r in vec_rows])
    semantics={'rows':32,'dimensions':8,'expected_contract':'NumPy mathematical dot product',
        'matches_numpy_dot':bool(np.allclose(actual,dot,rtol=1e-7,atol=1e-7)),
        'negative_f32_matches':bool(np.array_equal(actual,(-dot).astype(np.float32).astype(np.float64))),
        'negated_results_match_numpy_at_f32_tolerance':bool(np.allclose(-actual,dot,rtol=1e-6,atol=1e-6)),
        'max_absolute_error_after_negation':float(np.max(np.abs(-actual-dot))),
        'values':[{'id':i,'numpy_dot':float(dot[i]),'mo_inner_product':float(actual[i])} for i in range(32)],
        'reference':'https://docs.matrixorigin.cn/mo/en/v26.4.2.4/MatrixOne/Reference/Functions-and-Operators/Vector/inner_product.html'}
    (OUT/'vector-semantics.json').write_text(json.dumps(semantics,indent=2))
    # Confirm a useful SQL replacement without hiding the original TANH failure.
    def tanh_replacement():
        with c.cursor() as q:
            q.execute('SELECT AVG((EXP(2*x/100)-1)/(EXP(2*x/100)+1)) FROM ds')
            val=q.fetchone()[0]
        expected=np.tanh(dataset().x/100).mean(); assert equal(val,expected)
        return {'expression':'(EXP(2*z)-1)/(EXP(2*z)+1)','expected':expected,'actual':val,'domain':'z=x/100, bounded test values only'}
    save('tanh_bounded_domain_workaround',tanh_replacement)
    c.close(); e.dispose()
    (OUT/'type_checks.json').write_text(json.dumps(records,indent=2,ensure_ascii=False,default=str))

def bench(samples=512):
    c=connection()
    with c.cursor() as q:
        q.execute('CREATE TABLE IF NOT EXISTS perf_million(id BIGINT PRIMARY KEY,g INT,x DOUBLE,y DOUBLE)')
        q.execute('SELECT COUNT(*) FROM perf_million'); count=q.fetchone()[0]
        start=time.time()
        if count==0:
            q.execute('INSERT INTO perf_million SELECT a.id*128+b.id,MOD(a.id*128+b.id,100),a.x+b.x*0.01,a.y-b.y*0.01 FROM ds a CROSS JOIN ds b WHERE b.id<128')
        elif count!=1048576: raise RuntimeError(f'Unexpected performance dataset size {count}')
        load_seconds=time.time()-start
        q.execute('SELECT COUNT(*) FROM perf_million'); assert q.fetchone()[0]==1048576
    c.close()
    d=dataset(); x=np.repeat(d.x.to_numpy(),128)+np.tile(d.x.to_numpy()[:128]*.01,8192)
    y=np.repeat(d.y.to_numpy(),128)-np.tile(d.y.to_numpy()[:128]*.01,8192)
    g=np.arange(len(x))%100
    sums=np.bincount(g,weights=x,minlength=100)
    tests=[('full_scan','SELECT COUNT(*),SUM(x),AVG(x),STDDEV_POP(x) FROM perf_million',[(len(x),x.sum(),x.mean(),x.std())]),
      ('group_aggregate','SELECT g,COUNT(*),SUM(x),AVG(y) FROM perf_million GROUP BY g ORDER BY g',[(i,(g==i).sum(),sums[i],y[g==i].mean()) for i in range(100)]),
      ('filtered_scan','SELECT COUNT(*),SUM(x*y) FROM perf_million WHERE x>50',[(int((x>50).sum()),(x[x>50]*y[x>50]).sum())])]
    barrier=None
    def one(worker,indices):
        conn=connection(); result=[]
        with conn.cursor() as q:
            for j in [-2,-1]:
                _,sql,_=tests[j%len(tests)]; q.execute(sql); q.fetchall()
            barrier.wait()
            for j in indices:
                name,sql,expected=tests[j%len(tests)]
                t=time.perf_counter(); q.execute(sql); rows=q.fetchall(); ms=(time.perf_counter()-t)*1000
                ok=len(rows)==len(expected) and all(equal(a,b) for row,exp in zip(rows,expected) for a,b in zip(row,exp))
                result.append({'worker':worker,'sample':j,'workload':name,'query_ms':ms,'status':'pass' if ok else 'mismatch'})
                if not ok: raise AssertionError((name,rows[:3],expected[:3]))
        conn.close(); return result
    records=[]; summaries=[]
    for concurrency in (1,2,4,8):
        barrier=threading.Barrier(concurrency+1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(one,w,list(range(w,samples,concurrency))) for w in range(concurrency)]
            barrier.wait(); start=time.time()
            results=[future.result() for future in futures]
        elapsed=time.time()-start
        rows=[r for rr in results for r in rr]
        for r in rows: r['concurrency']=concurrency
        records.extend(rows)
        summaries.append({'concurrency':concurrency,'measured':samples,'warmup':2*concurrency,
            'measured_wall_seconds':elapsed,
            'measured_qps':samples/elapsed,
            'p50_ms':float(np.percentile([r['query_ms'] for r in rows],50)),
            'p95_ms':float(np.percentile([r['query_ms'] for r in rows],95)),
            'p99_ms':float(np.percentile([r['query_ms'] for r in rows],99))})
        print('BENCH',json.dumps(summaries[-1]),flush=True)
    (OUT/'benchmark.json').write_text(json.dumps({'rows':1048576,'load_seconds':load_seconds,'samples':records,'summary':summaries,
        'scope':'isolated single-node MO client query+fetch time, three mixed workloads; two warmups per worker, no JVM engines running'},indent=2))

def soak(seconds=120):
    c=connection()
    with c.cursor() as q:
        q.execute('CREATE TABLE IF NOT EXISTS soak_counter(id INT PRIMARY KEY,v BIGINT)')
        q.execute('TRUNCATE TABLE soak_counter')
        q.executemany('INSERT INTO soak_counter VALUES(%s,0)',[(i,) for i in range(8)])
    c.close(); start=time.time(); deadline=start+seconds
    def worker(w):
        c=connection(); c.autocommit(False); count=0; errors=[]; lats=[]
        while time.time()<deadline:
            t=time.perf_counter()
            try:
                with c.cursor() as q:
                    q.execute('UPDATE soak_counter SET v=v+1 WHERE id=%s',(w,)); c.commit()
                    count+=1
                    q.execute('UPDATE soak_counter SET v=v+1000 WHERE id=%s',(w,)); c.rollback()
                    q.execute('SELECT v FROM soak_counter WHERE id=%s',(w,)); actual=q.fetchone()[0]; c.commit()
                    if actual!=count: raise AssertionError(f'{actual}!={count}')
                lats.append((time.perf_counter()-t)*1000)
            except Exception as ex:
                errors.append(str(ex)); c.rollback()
                # A failure is preserved even if later iterations succeed.
                if len(errors)>=10: break
        c.close(); return {'worker':w,'committed_cycles':count,'errors':errors,
            'cycle_p50_ms':float(np.percentile(lats,50)) if lats else None,
            'cycle_p95_ms':float(np.percentile(lats,95)) if lats else None}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: workers=list(pool.map(worker,range(8)))
    c=connection()
    with c.cursor() as q: q.execute('SELECT id,v FROM soak_counter ORDER BY id'); final=q.fetchall()
    c.close()
    counts={w['worker']:w['committed_cycles'] for w in workers}
    result={'requested_seconds':seconds,'elapsed_seconds':time.time()-start,
        'concurrency':8,'workers':workers,'final_rows':final,
        'cycles':sum(counts.values()),'counter_verification':all(counts[i]==v for i,v in final),
        'scope':'8 independent rows, commit/rollback/readback; does not establish hot-row conflict handling or long-term reliability'}
    (OUT/'soak.json').write_text(json.dumps(result,indent=2)); print('SOAK',result['cycles'],'cycles',flush=True)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--bench-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.bench_only:
        # The initial short benchmark stays as an explicitly exploratory sample.
        old=OUT/'benchmark.json'
        if old.exists(): old.rename(OUT/'benchmark-initial-64.json')
        bench(); return
    stop=threading.Event(); thread=threading.Thread(target=monitor,args=(stop,OUT/'health.jsonl')); thread.start()
    try: type_checks(); bench(); soak()
    finally: stop.set(); thread.join()

if __name__=='__main__': main()
