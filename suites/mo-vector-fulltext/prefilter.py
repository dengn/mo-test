from suite import *
c=conn(timeout=90);qs=np.load(P/'queries.npy')
for on in [0,1]:
    sql(c,f'set enable_vector_prefilter_by_default={on}')
    for t in ['vh','vi']:
        for probes in ([8] if t=='vh' else [8,128]):
            sql(c,f'set probe_limit={probes}')
            for pred in ['where grp=99','where id between 1 and 100']:
                counts=[];recalls=[]
                for q in qs[:10]:
                    r=nearest(c,t,q,where=pred);ref=nearest(c,'vref',q,where=pred);counts.append(len(r));recalls.append(len(set(i for i,d in r)&set(i for i,d in ref))/10)
                plan=sql(c,f'explain select id from {t} {pred} order by l2_distance(v,%s) limit 10',(lit(qs[0]),));(P/f'prefilter-{on}-{t}-{probes}-{len(pred)}-plan.txt').write_text('\n'.join(str(r) for r in plan))
                emit('prefilter_control',on=on,table=t,nprobe=probes,predicate=pred,counts=counts,recall10_mean=float(np.mean(recalls)))
c.close()
