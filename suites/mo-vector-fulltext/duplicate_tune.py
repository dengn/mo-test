from suite import *
c=conn(timeout=240);v=np.load(P/'vectors.npy');ident=1100000228;sid=sql(c,'select source_id from ackledger where id=%s',(ident,))[0][0]
timed(c,'alter table vhm alter reindex ann hnsw m=32 ef_construction=200 ef_search=1000 force_sync')
for k in [10,64,128,256]:
    rows=nearest(c,'vhm',v[sid-1],k=k);emit('duplicate_ann_control',label='tuned_mutable',table='vhm',id=ident,source_id=sid,k=k,found=any(i==ident for i,d in rows),distance_zero_rows=sum(abs(d)<1e-6 for i,d in rows),same_source_rows=sql(c,'select count(*) from vhm where source_id=%s',(sid,))[0][0])
c.close()
