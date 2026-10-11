from suite import *
import hashlib
V=np.load(P/'vectors.npy')
def setup_mutation(c):
    for t in ['vhm','vim']:
        sql(c,f'create table {t}(id bigint primary key,v vecf32(128),source_id bigint)')
        sql(c,f'insert into {t} select id,v,id from vref where id<=1000')
    timed(c,"create index ann using hnsw on vhm(v) op_type 'vector_l2_ops'")
    timed(c,"create index ann using ivfflat on vim(v) lists=16 op_type 'vector_l2_ops'")
    for t in ['ftm','ft2m']:
        sql(c,f'create table {t}(id bigint primary key,body text)');sql(c,f"insert into {t} select id,'originalbase alpha beta gamma' from vref where id<=1000")
    timed(c,'create fulltext index txt on ftm(body)');timed(c,'create fulltext2 index txt on ft2m(body) max_index_capacity 10000')
    sql(c,'create table ackledger(id bigint primary key,source_id bigint,body text)')
def token(n):
    s=''
    while n:s=chr(97+n%26)+s;n//=26
    return 'zz'+s
def run(name,seconds=90,offset=0):
    qs=np.load(P/'queries.npy');journal=open(P/'acknowledged.jsonl','a',buffering=1)
    def worker(c,i,j):
        if i>=16:
            if (i+j)%2:nearest(c,'vhm',qs[(i+j)%30],k=10)
            else:sql(c,"select id from ft2m where match(body) against('+boundaryfresh +alpha' in boolean mode) limit 20")
            return
        ident=1000000000+offset+i*10000000+j
        sid=(ident%N)+1;body='boundaryfresh alpha beta gamma '+token(ident)
        try:
            c.begin()
            for t in ['vhm','vim']:sql(c,f'insert into {t} values(%s,%s,%s)',(ident,lit(V[sid-1]),sid))
            for t in ['ftm','ft2m']:sql(c,f'insert into {t} values(%s,%s)',(ident,body))
            sql(c,'insert into ackledger values(%s,%s,%s)',(ident,sid,body));c.commit()
            with lock:journal.write(json.dumps({'id':ident,'source_id':sid,'epoch':time.time()})+'\n')
        except Exception:
            try:c.rollback()
            except:pass
            raise
    phase(name,32,seconds,worker,timeout=10);journal.close()
def audit(c,label,wait_seconds=60):
    ack={json.loads(l)['id'] for l in (P/'acknowledged.jsonl').read_text().splitlines()}
    rows=sql(c,'select id from ackledger');ids={int(r[0]) for r in rows};emit('ack_audit',label=label,acknowledged=len(ack),ledger=len(ids),missing=len(ack-ids),ambiguous_commits=len(ids-ack))
    checks={}
    for t in ['vhm','vim']:
        checks[t]=sql(c,f'select count(*),sum(a.id is null),sum(l2_distance(a.v,b.v)>1e-6) from ackledger l left join {t} a on l.id=a.id left join vref b on l.source_id=b.id')
    for t in ['ftm','ft2m']:checks[t]=sql(c,f'select count(*),sum(a.id is null),sum(a.body!=l.body) from ackledger l left join {t} a on l.id=a.id')
    emit('transaction_audit',label=label,checks=checks)
    start=time.monotonic();last={}
    while True:
        for t in ['ftm','ft2m']:
            found={int(r[0]) for r in sql(c,f"select id from {t} where match(body) against('+boundaryfresh +alpha' in boolean mode)")}
            last[t]={'found':len(found),'missing_ledger':len(ids-found),'extra':len(found-ids),'pass_check':found==ids}
        if all(v['pass_check'] for v in last.values()) or time.monotonic()-start>=wait_seconds:break
        time.sleep(1)
    emit('fulltext_dml_visibility',label=label,observed_wait_seconds=time.monotonic()-start,result=last)
    # Rows are exact copies of their source vectors. Top-10 at the same point
    # must contain a distance-zero row, regardless of duplicates and tie order.
    samples=sorted(ids)[::max(1,len(ids)//20)][:20];result={}
    for t in ['vhm','vim']:
        misses=[]
        for ident in samples:
            sid=(ident%N)+1;r=nearest(c,t,V[sid-1],k=10)
            if not any(abs(float(d))<1e-6 for _,d in r):misses.append(ident)
        result[t]={'sampled':len(samples),'distance_zero_misses':misses}
    emit('vector_dml_visibility',label=label,result=result)
def maintenance(c):
    # Only seed rows are updated/deleted; acknowledged appended rows stay intact.
    c.begin()
    for t in ['vhm','vim']:
        sql(c,f'delete from {t} where id between 101 and 200')
        sql(c,f'update {t} set v=%s,source_id=100000 where id between 1 and 100',(lit(V[-1]),))
    for t in ['ftm','ft2m']:
        sql(c,f'delete from {t} where id between 101 and 200');sql(c,f"update {t} set body='changedbase omega delta' where id between 1 and 100")
    c.commit()
    emit('delete_update_committed',count_deleted_per_table=100,count_updated_per_table=100)
    start=time.monotonic()
    while True:
        results={}
        for t in ['ftm','ft2m']:
            changed={int(r[0]) for r in sql(c,f"select id from {t} where match(body) against('changedbase' in boolean mode)")}
            orig={int(r[0]) for r in sql(c,f"select id from {t} where match(body) against('originalbase' in boolean mode)")}
            results[t]={'changed_count':len(changed),'original_count':len(orig),'pass_check':changed==set(range(1,101)) and orig==set(range(201,1001))}
        if all(v['pass_check'] for v in results.values()) or time.monotonic()-start>60:break
        time.sleep(1)
    emit('delete_update_visibility',seconds=time.monotonic()-start,result=results)
    for t in ['vhm','vim']:
        r=nearest(c,t,V[-1],k=200);emit('updated_vector_search',table=t,count=len(r),deleted_ids_returned=[i for i,d in r if 101<=i<=200],updated_found=sum(1 for i,d in r if 1<=i<=100),max_updated_distance=max([d for i,d in r if 1<=i<=100] or [-1]))
    timed(c,'alter table ft2m alter reindex txt fulltext2 merge force_sync')
    timed(c,'alter table ft2m alter reindex txt fulltext2 force_sync')
    timed(c,'alter table vhm alter reindex ann hnsw force_sync')
    timed(c,'alter table vim alter reindex ann ivfflat lists=16')
    final={}
    for t in ['ftm','ft2m']:
        changed={int(r[0]) for r in sql(c,f"select id from {t} where match(body) against('changedbase' in boolean mode)")}
        orig={int(r[0]) for r in sql(c,f"select id from {t} where match(body) against('originalbase' in boolean mode)")}
        final[t]={'changed_count':len(changed),'original_count':len(orig),'pass_check':changed==set(range(1,101)) and orig==set(range(201,1001))}
    emit('delete_update_after_rebuild',result=final)
    for t in ['vhm','vim']:
        emit('vector_source_mutation',table=t,deleted_remaining=sql(c,f'select count(*) from {t} where id between 101 and 200'),updated_correct=sql(c,f'select count(*) from {t} where id between 1 and 100 and source_id=100000 and l2_distance(v,%s)<1e-6',(lit(V[-1]),)))
    audit(c,'after_maintenance')
if __name__=='__main__':
    (P/'load.pid').write_text(str(os.getpid()))
    try:
        cmd=sys.argv[1]
        if cmd=='setup':
            c=conn(timeout=180);setup_mutation(c);c.close()
        elif cmd=='run':run(sys.argv[2],int(sys.argv[3]),int(sys.argv[4]))
        elif cmd=='audit':
            c=conn(timeout=180);audit(c,sys.argv[2]);c.close()
        elif cmd=='maintenance':
            c=conn(timeout=300);maintenance(c);c.close()
    except Exception as e:emit('fatal',error=str(e),trace=traceback.format_exc());raise
