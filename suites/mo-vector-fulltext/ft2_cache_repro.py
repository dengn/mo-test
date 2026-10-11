from suite import *
c=conn(timeout=120);stor={}
for t in ['cache_early','cache_late']:
    sql(c,f'create table {t}(id bigint primary key,body text)');sql(c,f"insert into {t} values(1,'coldbasetoken')");sql(c,f'create fulltext2 index txt on {t}(body)')
    stor[t]=sql(c,"select index_table_name from mo_catalog.mo_indexes where name='txt' and algo='fulltext2' and algo_table_type='ftv2_index' and table_id in(select rel_id from mo_catalog.mo_tables where reldatabase=%s and relname=%s)",(DB,t))[0][0]
emit('cache_repro_warm',result=sql(c,"select id from cache_early where match(body) against('coldbasetoken')"))
for t in stor:sql(c,f"insert into {t} values(2,'cachefreshterm')")
start=time.monotonic();ready={}
while True:
    ready={t:sql(c,'select coalesce(max(chunk_id),-1) from `'+name.replace('`','``')+"` where index_id='cdc_tail' and tag=1")[0][0] for t,name in stor.items()}
    if all(n>=0 for n in ready.values()) or time.monotonic()-start>=120:break
    time.sleep(1)
emit('cache_repro_cdc_ready',wait_seconds=time.monotonic()-start,tail=ready)
c.close();c=conn(timeout=120)
for t in stor:
    r=sql(c,f"select id from {t} where match(body) against('cachefreshterm') order by id");emit('cache_repro_search',table=t,warmed_before_insert=(t=='cache_early'),result=r,expected=[[2]],pass_check=r==((2,),))
timed(c,'alter table cache_early alter reindex txt fulltext2 force_sync')
r=sql(c,"select id from cache_early where match(body) against('cachefreshterm') order by id");emit('cache_repro_after_rebuild',result=r,pass_check=r==((2,),));c.close()
