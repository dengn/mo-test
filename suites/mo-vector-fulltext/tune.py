from suite import *
c=conn(timeout=600)
for t in ['vh','vc']:
    timed(c,f'alter table {t} alter reindex ann hnsw m=32 ef_construction=200 ef_search=1000 force_sync')
    emit('tuned_schema',table=t,schema=sql(c,f'show create table {t}'))
oracle(c,'tuned')
qs=np.load(P/'queries.npy')
def work(c,i,j):nearest(c,'vh' if j%2 else 'vc',qs[(i+j)%30],'l2_distance' if j%2 else 'cosine_distance')
phase('hnsw_tuned_16',16,45,work)
c.close()
