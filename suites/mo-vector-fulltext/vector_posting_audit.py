from mutation import *
c=conn(timeout=180)
ids=sorted(int(i) for i, in sql(c,'select id from ackledger'))
samples=ids[::max(1,len(ids)//30)][:30]
for t in ['vhm','vim']:
    misses=[];controls=[]
    for ident in samples:
        sid=sql(c,'select source_id from ackledger where id=%s',(ident,))[0][0]
        duplicate_count=sql(c,f'select count(*) from {t} where source_id=%s',(sid,))[0][0]
        rows=nearest(c,t,V[sid-1],k=max(64,int(duplicate_count)+1))
        good=any(int(i)==ident and abs(float(d))<1e-6 for i,d in rows)
        if not good:misses.append(ident)
        controls.append({'id':ident,'source_id':sid,'same_source_rows':int(duplicate_count),'exact_ack_id_found':good})
    emit('vector_posting_ack_sample',table=t,sampled=len(samples),missing_exact_ack_ids=misses,controls=controls)
c.close()
