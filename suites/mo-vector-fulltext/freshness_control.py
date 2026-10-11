from suite import *
c=conn(timeout=120)
sql(c,'create table cache_cadence(id bigint primary key,body text)');sql(c,"insert into cache_cadence values(1,'cadenceoldterm')");sql(c,'create fulltext2 index txt on cache_cadence(body)')
sql(c,"select id from cache_cadence where match(body) against('cadenceoldterm')")
sql(c,'create table hnsw_cadence(id bigint primary key,v vecf32(128))');sql(c,'insert into hnsw_cadence select id,v from vref where id<=100')
sql(c,"create index ann using hnsw on hnsw_cadence(v) op_type 'vector_l2_ops'")
q=np.load(P/'vectors.npy')[40000];nearest(c,'hnsw_cadence',q)
cut=time.time_ns();sql(c,"insert into cache_cadence values(2,'cadencenewterm')");sql(c,'insert into hnsw_cadence values(999999,%s)',(lit(q),))
storage=sql(c,"select index_table_name from mo_catalog.mo_indexes where name='txt' and algo='fulltext2' and algo_table_type='ftv2_index' and table_id in(select rel_id from mo_catalog.mo_tables where reldatabase=%s and relname='cache_cadence')",(DB,))[0][0]
start=time.monotonic();ready=False
while time.monotonic()-start<120:
    tail=sql(c,'select coalesce(max(chunk_id),-1) from `'+storage.replace('`','``')+"` where index_id='cdc_tail' and tag=1")[0][0]
    jobs=sql(c,"select watermark from mo_catalog.mo_iscp_log where drop_at is null and table_id in(select rel_id from mo_catalog.mo_tables where reldatabase=%s and relname='hnsw_cadence')",(DB,))
    ready=tail>=0 and any(int(w.split('-')[0])>=cut for w, in jobs)
    if ready:break
    time.sleep(1)
emit('cadence_cdc_ready',ready=ready,seconds=time.monotonic()-start,tail=tail,hnsw_watermarks=jobs)
def observe(label):
    r=sql(c,"select id from cache_cadence where match(body) against('cadencenewterm')")
    v=nearest(c,'hnsw_cadence',q);h=any(i==999999 and abs(d)<1e-6 for i,d in v)
    emit('freshness_control',label=label,fulltext_result=r,fulltext_new_visible=(r==((2,),)),hnsw_new_id_visible=h)
    return r==((2,),) and h
observe('default_after_durable_cdc')
try:
    emit('freshness_override',result=sql(c,"select mo_ctl('cn','SetVectorIndexFreshnessInterval','1s')"))
    start=time.monotonic()
    while True:
        if observe('shortened_cadence') or time.monotonic()-start>30:break
        time.sleep(1)
    emit('freshness_convergence',seconds=time.monotonic()-start)
finally:
    emit('freshness_restored',result=sql(c,"select mo_ctl('cn','SetVectorIndexFreshnessInterval','0')"));c.close()
