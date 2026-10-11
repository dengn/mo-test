import json,hashlib,collections
from pathlib import Path
P=Path('/workspace/mo-corners-50000');cases=[]
def st(sql,params=None,expected=None,**kw):
 s={'sql':sql,'params':params or [],**kw}
 if expected is not None:s['expected']=expected
 return s
def add(module,family,steps,**kw):
 n=len(cases)+1;c={'id':f'K{n:06d}','module':module,'family':module+'.'+family,'steps':steps,**kw};c['operation_sha256']=hashlib.sha256(json.dumps({k:v for k,v in c.items() if k not in ['id','operation_sha256']},sort_keys=True,ensure_ascii=False).encode()).hexdigest();cases.append(c)
tls=['tls12','tls13','client','trusted','badca','badclient','expiredclient','badhost']
for i in range(8000):
 m=tls[i%8];add('tls',m,[st('select %s,sha2(%s,256)',[i,'tls_'+str(i)],[[i,hashlib.sha256(('tls_'+str(i)).encode()).hexdigest()]])],tls=m,connection_rejection=m in tls[4:])
authpattern='privilege|permission|access denied|authorized'
for i in range(8000):
 n=i+8001;k=i%8;params=[n]
 if k==0:s=st('select id,v from fixtures where id=%s',[i%200],[[i%200,(i%200)*13-700]]);family='table_read'
 elif k==1:s=st('select id,v from cv_read where id=%s',[i%200],[[i%200,(i%200)*13-700]]);family='view_read'
 elif k==2:s=st('insert into fixtures values(%s,0,0,\'denied\',\'{}\')',params,reject=True,error_pattern=authpattern);family='deny_insert'
 elif k==3:s=st('update fixtures set v=0 where id=%s',[-n],reject=True,error_pattern=authpattern);family='deny_update'
 elif k==4:s=st('delete from fixtures where id=%s',[-n],reject=True,error_pattern=authpattern);family='deny_delete'
 elif k==5:s=st(f'create table forbidden_k{n}(id int)',reject=True,error_pattern=authpattern);family='deny_ddl'
 elif k==6:s=st('update mo_catalog.mo_user set user_name=user_name where user_id=%s',[-n],reject=True,error_pattern=authpattern);family='deny_catalog_write'
 else:s=st('grant moadmin to corner_reader',reject=True,error_pattern=authpattern);family='deny_escalation'
 add('permissions',family,[s],actor='reader')
for i in range(10000):
 a=(i*1729)%2000000001-1000000000;b=(i*7919)%2000001-1000000;k=i%10;steps=[]
 if k==0:f='sql_nested';steps=[st('select cu_nested(%s,%s)',[a,b],[[(a+b)*2]])]
 elif k==1:f='sql_json';steps=[st('select cu_json(%s)',[json.dumps({'v':a})],[[a]])]
 elif k==2:f='python_scalar';steps=[st('select cu_pyadd(%s,%s)',[a,b],[[a+b]])]
 elif k==3:f='python_null';steps=[st('select cu_pyadd(null,%s)',[a],[[None]])]
 elif k==4:f='python_unicode';v=f"quote'\\newline\n中文😀_{i}";steps=[st('select cu_pystr(%s)',[v],[[v+'|中文😀']])]
 elif k==5:f='python_vector_batch';limit=1+i%197;steps=[st('select sum(cu_pyvec(id,v)) from fixtures where id<%s',[limit],[[sum(j+(j*13-700) for j in range(limit))]])]
 elif k==6:f='python_exception';steps=[st('select cu_pyerr(%s)',[a],reject=True,error_pattern='MO_CASE_INTENTIONAL_ERROR')]
 elif k==7:f='python_json';steps=[st('select cu_pyjson(cast(%s as json))',[json.dumps({'v':a})],[[a]])]
 elif k==8:f='python_decimal';v=f'{a%100000}.{i%10000:04d}';from decimal import Decimal;steps=[st('select cu_pydec(cast(%s as decimal(18,4)))',[v],[[str(Decimal(v)*2)]])]
 else:f='wrong_arity';steps=[st('select cu_pyadd(%s)',[a],reject=True,error_pattern='argument|parameter|function')]
 add('udf',f,steps)
for i in range(10000):
 n=i%37+1;v=i*997-4000000;k=i%10;cid=26001+i;kw={}
 if k==0:f='if_else';steps=[st('call cp_if(%s)',[v],[[-v if v<0 else v*2]])]
 elif k==1:f='while_loop';steps=[st('call cp_sum(%s)',[n],[[n*(n-1)//2]])]
 elif k==2:f='repeat_loop';steps=[st('call cp_repeat(%s)',[n],[[n]])]
 elif k==3:f='label_loop';steps=[st('call cp_loop(%s)',[n],[[n]])]
 elif k==4:f='nested_scope';steps=[st('call cp_scope(%s)',[n],[[n+2,n+1]])]
 elif k==5:f='inout';steps=[st('set @p=%s',[v]),st('call cp_io(@p)'),st('select @p',expected=[[v*3+1]])]
 elif k==6:f='json_parameter';steps=[st('call cp_json(%s)',[json.dumps({'v':v})],[[v]])]
 elif k==7:f='atomic_failure';kw['lock']='checkpoint';steps=[st('call cp_abort(%s,%s)',[cid,v],reject=True,error_pattern='cp_missing|no such table'),st('select count(*) from cp_atomic_sink where id=%s',[cid],[[0]]),st('select n from cp_checkpoint where id=1',expected=[[0]])]
 elif k==8:f='starlark_out';steps=[st('call cp_star(%s,@o)',[v]),st('select @o',expected=[[v*v+3]])]
 else:f='sql_mode_retained';steps=[st("set sql_mode=''"),st('call cp_mode(%s)',['mode_'+str(i)], [['mode_'+str(i)+'|mode']])]
 add('procedure',f,steps,**kw)
names=['ct_success','ct_gate_false','ct_gate_true','ct_abort','ct_error','ct_idempotent']
for i in range(6000):
 k=i%6;cid=36001+i;v=i*13;steps=[st('update ct_control set cid=%s,v=%s,ready=%s where kind=%s',[cid,v,int(k==2),k])]
 if k in [3,4]:steps.append(st('execute task '+names[k],reject=True,error_pattern='ct_missing|no such table'))
 else:steps.append(st('execute task '+names[k]))
 if k==5:steps.append(st('execute task '+names[k]))
 steps.append(st('select cid,v from ct_sink where cid=%s',[cid],[[cid,v]] if k in [0,2,5] else []))
 if k==3:steps.append(st('select n from cp_checkpoint where id=1',expected=[[0]]))
 if k==4:steps.append(st("select status from mo_task.sql_task_run where task_name='ct_error' order by run_id desc limit 1",expected=[['FAILED']]))
 add('task',names[k],steps,lock='checkpoint' if k==3 else names[k])
rows=[(i,i%17,i*13-700,'alpha' if i%2==0 else '中文😀') for i in range(1000)]
for i in range(8000):
 k=i%8;a=(i*17)%1000;b=min(1000,a+1+(i*37)%100);g=i%17;s=[r for r in rows if a<=r[0]<b]
 if k==0:f='filter_aggregate';steps=[st('select count(*),sum(v) from ice_events where id>=%s and id<%s',[a,b],[[len(s),str(sum(r[2] for r in s))]])]
 elif k==1:f='group_aggregate';steps=[st('select grp,count(*),sum(v) from ice_events where id>=%s and id<%s group by grp order by grp',[a,b],[[h,len([r for r in s if r[1]==h]),str(sum(r[2] for r in s if r[1]==h))] for h in sorted({r[1] for r in s})])]
 elif k==2:f='native_join';steps=[st('select a.id,a.v+b.v from ice_events a join fixtures b on a.id=b.id where a.id>=%s and a.id<%s order by a.id',[a,b],[[r[0],r[2]*2] for r in s if r[0]<200])]
 elif k==3:f='window';total=0;exp=[]
 else:steps=[]
 if k==3:
  for j,r in enumerate(s):total+=r[2];exp.append([r[0],j+1,str(total)])
  steps=[st('select id,row_number() over(order by id),sum(v) over(order by id rows unbounded preceding) from ice_events where id>=%s and id<%s order by id',[a,b],exp)]
 elif k==4:f='projection';steps=[st('select id,v,label from ice_events where id>=%s and id<%s order by id',[a,b],[[r[0],r[2],r[3]] for r in s])]
 elif k==5:f='unicode_filter';steps=[st('select id,label from ice_events where id>=%s and id<%s and label=%s order by id',[a,b,'中文😀'],[[r[0],r[3]] for r in s if r[0]%2])]
 elif k==6:f='cte';steps=[st('with a as(select id,v from ice_events where grp=%s),b as(select * from a where id>=%s and id<%s) select count(*),coalesce(sum(v),0) from b',[g,a,b],[[len([r for r in s if r[1]==g]),str(sum(r[2] for r in s if r[1]==g))]])]
 elif k==7:f='union';steps=[st('select id,v from ice_events where id=%s union all select id,v from ice_events where id=%s order by id',[a,b%1000],[[r[0],r[2]] for r in sorted([rows[a],rows[b%1000]])])]
 add('iceberg',f,steps)
assert len(cases)==50000
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False)+'\n')
coverage={'total':len(cases),'modules':dict(collections.Counter(c['module'] for c in cases)),'families':dict(collections.Counter(c['family'] for c in cases)),'unique_operations':len({c['operation_sha256'] for c in cases})}
(P/'coverage.json').write_text(json.dumps(coverage,indent=2,ensure_ascii=False));print(json.dumps(coverage,ensure_ascii=False))
