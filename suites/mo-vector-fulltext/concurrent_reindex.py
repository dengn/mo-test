from suite import *
qs=np.load(P/'queries.npy')
ops=['alter table ft2m alter reindex txt fulltext2 merge force_sync','alter table ft2m alter reindex txt fulltext2 force_sync','alter table vhm alter reindex ann hnsw force_sync','alter table vim alter reindex ann ivfflat lists=16']
def work(c,i,j):
    if i==0 and j<len(ops):timed(c,ops[j])
    elif i%2:nearest(c,'vhm',qs[(i+j)%30],k=20)
    else:sql(c,"select id from ft2m where match(body) against('+boundaryfresh +alpha' in boolean mode) limit 100")
phase('concurrent_reindex_16',16,75,work,timeout=120)
