import os,time,json,math,threading,collections,concurrent.futures,traceback,sys
from pathlib import Path
import pymysql
import numpy as np
P=Path('/workspace/mo-vector-fulltext')
N=100000; D=60000; DIM=128
DB=(P/'database.txt').read_text().strip() if (P/'database.txt').exists() else 'mo_vecft_'+str(time.time_ns())
(P/'database.txt').write_text(DB+'\n')
lock=threading.Lock()
def emit(kind,**v):
    v=dict(kind=kind,epoch=time.time(),**v)
    with lock:
        with open(P/'results.jsonl','a') as f:f.write(json.dumps(v,ensure_ascii=False,default=str)+'\n')
        print(json.dumps(v,ensure_ascii=False,default=str),flush=True)
def conn(db=DB,timeout=90):
    c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=db,autocommit=True,connect_timeout=5,read_timeout=timeout,write_timeout=timeout,charset='utf8mb4')
    with c.cursor() as q:
        for s in ['set experimental_hnsw_index=1','set experimental_fulltext2_index=1','set hnsw_threads_build=4','set hnsw_threads_search=1','set probe_limit=8']:
            q.execute(s)
    return c
def sql(c,s,args=None):
    with c.cursor() as q:q.execute(s,args);return q.fetchall()
def timed(c,s,args=None):
    t=time.monotonic()
    try:
        r=sql(c,s,args);emit('sql',sql=s[:300],seconds=time.monotonic()-t,rows=len(r),sample=r[:3]);return r
    except Exception as e:emit('sql_error',sql=s[:300],seconds=time.monotonic()-t,error=str(e));raise
def lit(v):return '['+','.join(format(float(x),'.8g') for x in v)+']'
def load_vectors(c):
    rng=np.random.default_rng(20261009)
    v=rng.standard_normal((N,DIM),dtype=np.float32);v/=np.linalg.norm(v,axis=1)[:,None]
    np.save(P/'vectors.npy',v)
    for t in ['vref','vh','vc','vi']:sql(c,f'create table {t}(id bigint primary key,v vecf32({DIM}),grp int)')
    def part(a,b):
        x=conn()
        try:
            for start in range(a,b,200):
                rows=[(i+1,lit(v[i]),(i+1)%100) for i in range(start,min(start+200,b))]
                with x.cursor() as q:q.executemany('insert into vref values(%s,%s,%s)',rows)
        finally:x.close()
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(4) as ex:list(ex.map(lambda ab:part(*ab),[(i*N//4,(i+1)*N//4) for i in range(4)]))
    emit('seed_vectors',count=N,dimension=DIM,seconds=time.monotonic()-t)
    for t in ['vh','vc','vi']:timed(c,f'insert into {t} select * from vref')
    timed(c,"create index ann using hnsw on vh(v) op_type 'vector_l2_ops'")
    timed(c,"create index ann using hnsw on vc(v) op_type 'vector_cosine_ops'")
    timed(c,"create index ann using ivfflat on vi(v) lists=128 op_type 'vector_l2_ops'")
    for t in ['vh','vc']:timed(c,f'alter table {t} alter reindex ann hnsw force_sync')
    rng=np.random.default_rng(1536);hi=rng.standard_normal((5000,1536),dtype=np.float32);hi/=np.linalg.norm(hi,axis=1)[:,None];np.save(P/'highdim.npy',hi)
    sql(c,'create table vd(id bigint primary key,v vecf32(1536))')
    for i in range(0,5000,100):
        with c.cursor() as q:q.executemany('insert into vd values(%s,%s)',[(j+1,lit(hi[j])) for j in range(i,i+100)])
    timed(c,"create index ann using hnsw on vd(v) op_type 'vector_l2_ops'")
def load_docs(c):
    for t in ['ft','ft2']:sql(c,f'create table {t}(id bigint primary key,body text,grp int)')
    patterns=['alpha beta gamma quick brown fox','alpha beta gamma brown quick fox','alpha beta delta quick red fox','alpha gamma delta quick brown dog','beta gamma delta lazy brown fox','omega delta sleepy owl','alpha beta gamma quick brown fox quick brown fox','omega beta red cat']
    def part(a,b):
        x=conn()
        try:
            for start in range(a,b,250):
                rows=[(i,(patterns[i%8]+' ')*20+' tok'+str(i),i%100) for i in range(start,min(start+250,b))]
                with x.cursor() as q:q.executemany('insert into ft values(%s,%s,%s)',rows)
        finally:x.close()
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(4) as ex:list(ex.map(lambda ab:part(*ab),[(i*D//4+1,(i+1)*D//4+1) for i in range(4)]))
    emit('seed_docs',count=D,seconds=time.monotonic()-t)
    timed(c,'insert into ft2 select * from ft')
    timed(c,'create fulltext index txt on ft(body)')
    timed(c,'create fulltext2 index txt on ft2(body) max_index_capacity 20000')
def nearest(c,t,v,metric='l2_distance',k=10,where=''):
    s=f'select id,{metric}(v,%s) as d from {t} {where} order by {metric}(v,%s) limit {int(k)}'
    return sql(c,s,(lit(v),lit(v)))
def oracle(c,label='baseline'):
    v=np.load(P/'vectors.npy');rng=np.random.default_rng(777)
    qs=rng.standard_normal((30,DIM),dtype=np.float32);qs/=np.linalg.norm(qs,axis=1)[:,None];np.save(P/'queries.npy',qs)
    for table,metric in [('vh','l2_distance'),('vc','cosine_distance'),('vi','l2_distance')]:
        plan=sql(c,f'explain select id from {table} order by {metric}(v,%s) limit 10',(lit(qs[0]),));(P/f'{label}-{table}-plan.txt').write_text('\n'.join(str(r) for r in plan))
        rec=[];errs=[];score=[];lat=[]
        for j,q in enumerate(qs):
            dist=np.sum((v.astype(np.float64)-q.astype(np.float64))**2,axis=1) if metric=='l2_distance' else 1-(v.astype(np.float64)@q.astype(np.float64))/(np.linalg.norm(v.astype(np.float64),axis=1)*np.linalg.norm(q.astype(np.float64)))
            expected=set((np.argsort(dist)[:10]+1).tolist());st=time.monotonic()
            try:
                rows=nearest(c,table,q,metric);lat.append(time.monotonic()-st);ids=[int(r[0]) for r in rows];rec.append(len(expected.intersection(ids))/10)
                score.append(max([abs(float(d)-(math.sqrt(dist[i-1]) if metric=='l2_distance' else dist[i-1])) for i,d in rows] or [0]))
                if len(ids)!=10 or len(set(ids))!=10 or any(i<1 or i>N for i in ids):errs.append({'query':j,'ids':ids})
                if j<3:
                    ref=nearest(c,'vref',q,metric);emit('exact_crosscheck',label=label,table=table,query=j,numpy_sql_top10_equal=set(int(r[0]) for r in ref)==expected)
            except Exception as e:errs.append(str(e))
        emit('recall',label=label,table=table,queries=30,recall10_mean=float(np.mean(rec)) if rec else None,recall10_min=min(rec) if rec else None,max_score_error=max(score) if score else None,p99_ms=float(np.percentile(lat,99)*1000) if lat else None,errors=errs)
    sql(c,'set probe_limit=128')
    recall=[]
    for q in qs[:10]:
        ref=nearest(c,'vref',q);r=nearest(c,'vi',q);recall.append(len(set(i for i,d in ref)&set(i for i,d in r))/10)
    emit('ivf_full_probe',label=label,queries=10,mean_recall=float(np.mean(recall)),minimum=min(recall));sql(c,'set probe_limit=8')
    cases=[('+alpha +beta',[0,1,2,6]),('+alpha -gamma',[2]),('quic*',[0,1,2,3,6]),('+quick +fox',[0,1,2,6]),('+quick +quick +fox',[0,1,2,6]),('+alpha +missing',[])]
    for t in ['ft','ft2']:
        for query,classes in cases:
            rows=sql(c,f"select id from {t} where match(body) against(%s in boolean mode)",(query,));actual={int(r[0]) for r in rows};expected={i for i in range(1,D+1) if i%8 in classes}
            emit('ft_membership',label=label,table=t,query=query,count=len(actual),expected=len(expected),missing=len(expected-actual),extra=len(actual-expected),pass_check=actual==expected)
    for query,classes in [('quick brown fox',[0,6]),('brown quick',[1]),('quick missing',[])]:
        rows=sql(c,'select id from ft2 where match(body) against(%s)',(query,));actual={int(r[0]) for r in rows};expected={i for i in range(1,D+1) if i%8 in classes}
        emit('phrase_membership',label=label,query=query,count=len(actual),missing=len(expected-actual),extra=len(actual-expected),pass_check=actual==expected)
def phase(name,workers,seconds,fn,timeout=15):
    (P/'load.pid').write_text(str(os.getpid()))
    stop=time.monotonic()+seconds
    def worker(i):
        good=0;attempt=0;bad=collections.Counter();samples={};lat=[];c=None
        while time.monotonic()<stop:
            t=time.monotonic()
            try:
                if c is None:c=conn(timeout=timeout)
                fn(c,i,attempt);good+=1
            except Exception as e:
                key=str(e)[:180];bad[key]+=1;samples[key]=repr(e)
                if isinstance(e,(pymysql.err.OperationalError,pymysql.err.InterfaceError)):
                    try:c.close()
                    except:pass
                    c=None
                    time.sleep(.02)
            lat.append((time.monotonic()-t)*1000)
            attempt+=1
        if c:c.close()
        return good,bad,lat
    t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:res=list(ex.map(worker,range(workers)))
    elapsed=time.monotonic()-t;bad=collections.Counter();lat=[]
    for n,e,l in res:bad.update(e);lat.extend(l)
    emit('phase',name=name,workers=workers,requested_seconds=seconds,seconds=elapsed,success=sum(r[0] for r in res),errors=dict(bad),ops_s=sum(r[0] for r in res)/elapsed,p50_ms=float(np.percentile(lat,50)),p99_ms=float(np.percentile(lat,99)))
def stress():
    qs=np.load(P/'queries.npy');hi=np.load(P/'highdim.npy')
    def vec(c,i,j):
        t=['vh','vc','vi'][j%3];nearest(c,t,qs[(i+j)%30],'cosine_distance' if t=='vc' else 'l2_distance',10 if j%5 else 100)
    def ft(c,i,j,t=None):
        t=t or ['ft','ft2'][j%2];query=['+alpha +beta','quic*','+quick +fox','+omega -beta','"quick brown fox"'][j%5]
        sql(c,f'select id,match(body) against(%s in boolean mode) as score from {t} where match(body) against(%s in boolean mode) order by score desc limit 100',(query,query))
    def high(c,i,j):nearest(c,'vd',hi[(i*31+j)%5000],k=100)
    phase('vector_16',16,60,vec);phase('vector_128',128,75,vec)
    for table in ['ft','ft2']:
        phase(table+'_16',16,45,lambda c,i,j:ft(c,i,j,table));phase(table+'_128',128,60,lambda c,i,j:ft(c,i,j,table))
    phase('vector_1536dim_64',64,60,high)
    def mixed(c,i,j):vec(c,i,j) if (i+j)%2 else ft(c,i,j)
    phase('vector_fulltext_256',256,90,mixed)
    phase('cooldown_probe_4',4,20,lambda c,i,j:sql(c,'select 1'))
def setup():
    c=conn(None,600);sql(c,f'create database {DB}');sql(c,f'use {DB}');emit('setup',database=DB,pid=os.getpid(),version=sql(c,'select version()'))
    load_vectors(c);load_docs(c);oracle(c);c.close()
if __name__=='__main__':
    (P/'load.pid').write_text(str(os.getpid()))
    try:
        if sys.argv[1]=='setup':setup()
        elif sys.argv[1]=='stress':stress()
        elif sys.argv[1]=='oracle':
            c=conn(timeout=180);oracle(c,sys.argv[2] if len(sys.argv)>2 else 'audit');c.close()
    except Exception as e:emit('fatal',error=str(e),trace=traceback.format_exc());raise
