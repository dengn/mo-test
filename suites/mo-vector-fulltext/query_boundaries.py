from suite import *
c=conn(timeout=90);qs=np.load(P/'queries.npy')
emit('filter_settings',values=sql(c,"show variables like 'enable_vector_prefilter_by_default'"))
for table,metric in [('vh','l2_distance'),('vc','cosine_distance'),('vi','l2_distance')]:
    for pred in ['where grp=99','where id between 1 and 100','where id<0']:
        vals=[]
        for j,q in enumerate(qs[:10]):
            r=nearest(c,table,q,metric,10,pred);ref=nearest(c,'vref',q,metric,10,pred)
            ids={int(i) for i,d in r};expected={int(i) for i,d in ref};valid=all((i%100==99 if pred=='where grp=99' else 1<=i<=100 if pred=='where id between 1 and 100' else False) for i in ids)
            vals.append({'query':j,'count':len(r),'exact_count':len(ref),'recall':len(ids&expected)/len(expected) if expected else 1,'filter_valid':valid})
        plan=sql(c,f'explain select id from {table} {pred} order by {metric}(v,%s) limit 10',(lit(qs[0]),));(P/(table+'-'+str(['where grp=99','where id between 1 and 100','where id<0'].index(pred))+'-filtered-plan.txt')).write_text('\n'.join(str(r) for r in plan))
        emit('filtered_vector',table=table,predicate=pred,results=vals)
    for k in [0,1,1000,10000,100001]:
        start=time.monotonic()
        try:
            if table=='vi':sql(c,'set probe_limit='+str(128 if k>=1000 else 8))
            r=nearest(c,table,qs[0],metric,k);ids=[int(i) for i,d in r];ds=[float(d) for i,d in r]
            emit('limit_boundary',table=table,k=k,count=len(r),seconds=time.monotonic()-start,unique=len(set(ids)),scores_sorted=all(a<=b+1e-6 for a,b in zip(ds,ds[1:])),ids_valid=all(1<=i<=N for i in ids))
        except Exception as e:emit('limit_boundary',table=table,k=k,seconds=time.monotonic()-start,error=str(e))
    sql(c,'set probe_limit=8')
    try:nearest(c,table,[1,2,3],metric);emit('wrong_query_dimension',table=table,rejected=False)
    except Exception as e:emit('wrong_query_dimension',table=table,rejected=True,error=str(e))
# Terminal consumers of ANN top-k must preserve the same candidate cardinality.
for t in ['vh','vi']:
    q=lit(qs[1]);s=f'select id,l2_distance(v,%s) as d from {t} order by l2_distance(v,%s) limit 10'
    r=sql(c,s,(q,q));aggregate=sql(c,'select count(*),sum(id),min(d),max(d) from ('+s+') x',(q,q))
    emit('ann_derived_aggregate',table=t,aggregate=aggregate,expected_count=len(r),expected_sum=sum(i for i,d in r),pass_check=int(aggregate[0][0])==len(r) and int(aggregate[0][1])==sum(i for i,d in r))
emit('boundary_cooldown',result=sql(c,'select 1'));c.close()
