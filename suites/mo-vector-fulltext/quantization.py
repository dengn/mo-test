from suite import *
c=conn(timeout=240);v=np.load(P/'vectors.npy');qs=np.load(P/'queries.npy')
sql(c,'create table vq(id bigint primary key,v vecf32(128),grp int)');timed(c,'insert into vq select * from vref')
timed(c,"create index ann using ivfflat on vq(v) lists=128 op_type 'vector_l2_ops' quantization 'int8'")
sql(c,'set probe_limit=128')
def check(label):
    recalls=[];errors=[]
    for q in qs[:10]:
        r=nearest(c,'vq',q);ref=nearest(c,'vref',q);recalls.append(len(set(i for i,d in r)&set(i for i,d in ref))/10)
        errors.append(max([abs(float(d)-float(np.linalg.norm(v[i-1].astype(np.float64)-q.astype(np.float64)))) for i,d in r] or [0]))
    emit('int8_quantization',label=label,queries=10,nprobe=128,recall10_mean=float(np.mean(recalls)),recall10_min=min(recalls),max_score_error=max(errors))
check('initial')
timed(c,'create table vqclone clone vq')
for j,q in enumerate(qs[:10]):
    a=nearest(c,'vq',q);b=nearest(c,'vqclone',q);emit('quantized_clone',query=j,pass_check=a==b)
timed(c,"alter table vq add column note varchar(10) default 'boundary'")
timed(c,'alter table vq alter reindex ann ivfflat lists=128')
check('after_alter_reindex')
emit('quantization_schema',schema=sql(c,'show create table vq'));c.close()
