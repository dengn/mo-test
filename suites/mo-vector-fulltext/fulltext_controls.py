from suite import *
c=conn(timeout=120)
cases=[('+alpha +beta',[0,1,2,6]),('quic*',[0,1,2,3,6]),('+quick +fox',[0,1,2,6]),('+omega -beta',[5]),('"quick brown fox"',[0,6])]
for table in ['ft','ft2']:
    for query,classes in cases:
        start=time.monotonic()
        try:
            r=sql(c,f'select id,match(body) against(%s in boolean mode) as score from {table} where match(body) against(%s in boolean mode) order by score desc limit 100',(query,query))
            scores=[float(score) for i,score in r]
            emit('ft_single_control',table=table,query=query,seconds=time.monotonic()-start,count=len(r),membership_valid=all(int(i)%8 in classes for i,s in r),unique=len(set(int(i) for i,s in r)),finite_scores=all(math.isfinite(s) for s in scores),scores_sorted=all(a>=b-1e-6 for a,b in zip(scores,scores[1:])))
        except Exception as e:emit('ft_single_control',table=table,query=query,seconds=time.monotonic()-start,error=str(e))
emit('control_probe',result=sql(c,'select 1'));c.close()
