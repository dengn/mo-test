import json,hashlib,random,math,collections,sys
from pathlib import Path
B=Path('/workspace/mo-cases-50000');P=Path(__file__).resolve().parent;R=random.Random(101050000);F=json.loads((B/'fixtures.json').read_text());seed=F['seed'];docs={int(k):v for k,v in F['docs'].items()};seen=set();cases=[]
S=json.loads((B/'source-manifest.json').read_text());sources=[x['source_id'] for x in S if x['status']=='downloaded' and any(v in x['path'] for v in ['subselect.test','window_functions.test','vector-contract-hardening','fulltext2_stability/oracle.py','replace_into.sql'])]
def add(module,family,sql,params=None,expected=None,diff=False,policy='normal',steps=None,meta=None):
 st=steps or [{'sql':sql,'params':params or []}];core={'statements':st,'policy':policy,'meta':meta};h=hashlib.sha256(json.dumps(core,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 if h in seen:return
 seen.add(h);cases.append(dict(id=f'H{len(cases)+1:05d}',module=module,family=family,statements=st,expected=expected,mysql_differential=diff,expect_error=False,compare_mode='ordered',tolerance=2e-5 if module=='chaos_search' else 1e-6,sources=sources,sql_sha256=h,oracle_policy=policy,meta=meta))
def fill(module,n,fn):
 j=0
 while sum(c['module']==module for c in cases)<n:fn(j);j+=1
 print(module,n,flush=True)
def complex(j):
 a=R.randint(-10000,10000);lo=R.randint(1,150);hi=R.randint(lo,200);g=R.randint(0,16);k=j%15
 queries=[
 ('mixed_case_decimal_json',"select id,case when nullable is null then cast(val as decimal(20,3)) else cast(json_unquote(json_extract(json_object('n',nullable),'$.n')) as decimal(20,3)) end from seed where id between %s and %s order by id",[lo,hi]),
 ('cte_join_window',"with a as(select id,grp,val from seed where id between %s and %s),b as(select grp,sum(val) z from seed group by grp) select a.id,cast(a.val+b.z as decimal(25,4)),row_number() over(partition by a.grp order by a.id) from a join b on a.grp=b.grp order by a.id",[lo,hi]),
 ('correlated_json_exists',"select s.id,concat(name,':',cast(val as char)) from seed s where id between %s and %s and exists(select 1 from seed t where t.grp=s.grp and cast(json_unquote(json_extract(json_object('x',t.val),'$.x')) as signed)>%s) order by s.id",[lo,hi,a]),
 ('union_mixed_null',"select id,cast(val as decimal(24,4)) v from seed where id between %s and %s union all select id,cast(nullable as decimal(24,4)) from seed where grp=%s order by id,v",[lo,hi,g]),
 ('nested_derived_aggregate',"select grp,count(*),cast(sum(z) as decimal(28,3)) from(select x.id,x.grp,coalesce(x.val,y.nullable,%s) z from seed x left join seed y on x.id=y.id+7 where x.id between %s and %s) q group by grp order by grp",[a,lo,hi]),
 ('window_decimal_null',"select id,cast(avg(cast(coalesce(nullable,val) as decimal(20,4))) over(order by id rows between 3 preceding and 2 following) as decimal(25,4)) from seed where id between %s and %s order by id",[lo,hi]),
 ('date_case_group',"select grp,date_format(date_add('2020-01-01',interval mod(sum(val)+%s,365) day),'%%Y-%%m-%%d'),count(nullable) from seed where id between %s and %s group by grp order by grp",[a,lo,hi]),
 ('mixed_predicate_coercion',"select id from seed where id between %s and %s and (cast(val as char)>cast(%s as char) or nullable is null) and coalesce(cast(nullable as decimal(20,3)),0)>=0 order by id",[lo,hi,a]),
 ('anti_join_null',"select x.id,case when y.id is null then 'missing' else cast(y.val as char) end from seed x left join seed y on y.id=x.id+%s where x.id between %s and %s and not exists(select 1 from seed z where z.id=x.id and z.nullable=%s) order by x.id",[g+1,lo,hi,g]),
 ('cte_union_distinct',"with a as(select id,val from seed where id between %s and %s),b as(select id,val from seed where grp=%s) select distinct id,cast(val as decimal(20,4)) from(select * from a union all select * from b) q order by id",[lo,hi,g]),
 ('scalar_subquery_coercion',"select s.id,cast((select max(t.val) from seed t where t.grp=s.grp) as char),coalesce(nullable,%s) from seed s where s.id between %s and %s order by s.id",[a,lo,hi]),
 ('json_case_order',"select id,json_unquote(json_extract(json_object('x',case when nullable is null then name else cast(nullable as char) end),'$.x')) v from seed where id between %s and %s order by v,id",[lo,hi]),
 ('having_nested_decimal',"select grp,sum(cast(val as decimal(20,3))) from seed where id between %s and %s group by grp having sum(cast(val as decimal(20,3)))>%s and count(*)>1 order by grp",[lo,hi,a]),
 ('rank_join',"select x.id,rank() over(partition by x.grp order by coalesce(y.nullable,%s),x.id),dense_rank() over(order by x.val) from seed x join seed y on x.id=y.id where x.id between %s and %s order by x.id",[a,lo,hi]),
 ('null_safe_correlated',"select s.id from seed s where id between %s and %s and (select count(*) from seed t where t.nullable <=> s.nullable and t.grp=%s)>0 order by s.id",[lo,hi,g])]
 f,s,p=queries[k];add('chaos_complex','complex.'+f,s,p,diff=True)
def search(j):
 lo=R.randint(1,150);hi=R.randint(lo,200);g=R.randint(0,16);q=[R.randint(-1000,1000)/128 for _ in range(3)];lit=json.dumps(q);k=j%10;word=R.choice(['alpha','beta','gamma','omega','fox','dog']);table='ft2' if j%2 else 'ft';term='tok'+chr(97+j%26)+chr(97+(j//26)%26)
 rows=[x for x in seed if lo<=x[0]<=hi];dist=lambda i:math.sqrt(sum((((i*17+t*11)%101-50)/10-q[t])**2 for t in range(3)))
 if k in [0,1,2]:
  chosen=[r[0] for r in rows if (k!=1 or r[1]==g) and (k!=2 or word in docs[r[0]].split())];n=1+j%20;ids=sorted(chosen,key=lambda i:(dist(i),i))[:n]
  join=f' join {table} f on f.id=v.id' if k==2 else '';pred=' and s.grp=%s' if k==1 else (' and match(f.body) against(%s in boolean mode)' if k==2 else '')
  p=[lit,lo,hi]+([g] if k==1 else ([word] if k==2 else []));s=f'select v.id,l2_distance(v.v,%s) d from vectors v join seed s on v.id=s.id{join} where s.id between %s and %s{pred} order by d,v.id limit {n}'
  e=[[i,dist(i)] for i in ids];f=['vector_join_topk','vector_group_filter','hybrid_fulltext_topk'][k]
 elif k==3:
  s=f"with c as(select f.id from {table} f where match(body) against(%s in boolean mode)) select s.id,cast(s.val as decimal(20,3)),l2_norm(v.v) from c join seed s on c.id=s.id join vectors v on v.id=c.id where s.id between %s and %s order by s.id";p=[word,lo,hi];e=[[r[0],r[2],math.sqrt(sum((((r[0]*17+t*11)%101-50)/10)**2 for t in range(3)))] for r in rows if word in docs[r[0]].split()];f='fulltext_cte_decimal_vector'
 elif k==4:
  s="select s.id,case when s.nullable is null then null else cosine_distance(v.v,cast(%s as vecf32(3))) end from seed s left join vectors v on s.id=v.id where s.id between %s and %s order by s.id";p=[lit,lo,hi];e=[]
  for r in rows:
   vv=[((r[0]*17+t*11)%101-50)/10 for t in range(3)];z=math.sqrt(sum(x*x for x in vv)*sum(x*x for x in q));e.append([r[0],None if r[3] is None else 1-sum(x*y for x,y in zip(vv,q))/z])
  f='vector_case_null'
 elif k==5:
  s=f'select s.grp,count(*),sum(s.val) from {table} f join seed s on f.id=s.id where match(f.body) against(%s in boolean mode) and s.id between %s and %s group by s.grp order by s.grp';p=[word,lo,hi];rs=[r for r in rows if word in docs[r[0]].split()];e=[[g,len([r for r in rs if r[1]==g]),sum(r[2] for r in rs if r[1]==g)] for g in sorted({r[1] for r in rs})];f='fulltext_group_aggregate'
 elif k==6:
  s=f'select s.id,row_number() over(order by s.id),cast(s.val as char) from seed s where id between %s and %s and exists(select 1 from {table} f where f.id=s.id and match(body) against(%s in boolean mode)) order by s.id';p=[lo,hi,word];rs=[r for r in rows if word in docs[r[0]].split()];e=[[r[0],i+1,str(r[2])] for i,r in enumerate(rs)];f='fulltext_correlated_window'
 elif k==7:
  s="select id,inner_product(v,cast(%s as vecf32(3))),l1_distance(v,cast(%s as vecf32(3))) from vectors where id between %s and %s order by id";p=[lit,lit,lo,hi];e=[[r[0],-sum(((r[0]*17+t*11)%101-50)/10*q[t] for t in range(3)),sum(abs(((r[0]*17+t*11)%101-50)/10-q[t]) for t in range(3))] for r in rows];f='mixed_metric_projection'
 elif k==8:
  s=f'select s.id,json_unquote(json_extract(json_object(\'name\',s.name),\'$.name\')) from seed s join {table} f on s.id=f.id where match(body) against(%s in boolean mode) and s.id between %s and %s order by s.id';p=[word,lo,hi];e=[[r[0],r[4]] for r in rows if word in docs[r[0]].split()];f='fulltext_json_join'
 else:
  s="select v.id,l2_distance(v.v,cast(%s as vecf64(3))) from vectors v where id between %s and %s and id in(select id from seed where nullable is null) order by id";p=[lit,lo,hi];e=[[r[0],dist(r[0])] for r in rows if r[3] is None];f='mixed_vector_width_subquery'
 add('chaos_search','search.'+f,s,p,e)
def boundary(j):
 k=j%12;n=j+1;v=R.randint(-10**18,10**18)
 if k==0:s,p,f='select cast(%s as tinyint),cast(%s as unsigned)',[str(v),str(v)],'integer_overflow'
 elif k==1:s,p,f='select cast(%s as decimal(5,2))',[str(v)+'.999'],'decimal_overflow'
 elif k==2:d=[1,2,3,64,1024,4096,8192][j%7];s,p,f=f'select cast(%s as vecf32({d}))',[json.dumps([n/128]*(d-1))],'vector_dimension'
 elif k==3:s,p,f='select l2_distance(cast(%s as vecf64(2)),cast(%s as vecf64(2)))',[f'[{n}e200,1e200]','[0,0]'],'vector_nonfinite_metric'
 elif k==4:s,p,f='select normalize_l2(cast(%s as vecf32(3))),cosine_distance(cast(%s as vecf32(3)),cast(%s as vecf32(3)))',['[0,0,0]',f'[{n},0,0]','[0,0,0]'],'vector_zero_norm'
 elif k==5:s,p,f='select json_extract(%s,%s)',['['*(32+j%256)+str(n)+']'*(31+j%256),'$[0]'],'json_depth_invalid'
 elif k==6:s,p,f='select json_extract(%s,%s)',[json.dumps({'x':n}),'$.'+('['*(1+j%50))],'json_path_invalid'
 elif k==7:s,p,f='select length(lpad(%s,%s,%s)),length(repeat(%s,%s))',[str(n),4096+j%61440,'中文😀',str(n),j%2000],'string_growth'
 elif k==8:s,p,f='select '+('('* (32+j%96))+'%s'+(')'*(32+j%96)),[v],'expression_depth'
 elif k==9:
  size=32+j%512;s='select %s in('+','.join('%s' for _ in range(size))+')';p=[v]+[R.randint(-10**10,10**10) for _ in range(size)];f='in_list_width'
 elif k==10:s,p,f='select cast(%s as date),cast(%s as datetime)',[str(19000000+j),str(99990000+j)],'date_invalid'
 else:s,p,f='select case when %s>0 then cast(%s as decimal(38,20)) else json_extract(%s,\'$.x\') end',[v,str(v),json.dumps({'x':n})],'heterogeneous_case'
 add('chaos_boundaries','boundary.'+f,s,p,policy='robustness')
def mixed(j):
 i=j+1;a=R.randint(-10**8,10**8);text='中文😀token'+str(i);g=j%17;k=j%5;steps=[]
 def st(s,p=None):steps.append({'sql':s,'params':p or []})
 st('begin');st('insert into chaos_ledger(id,n,body,j) values(%s,%s,%s,%s)',[i,a,text,json.dumps({'x':a,'s':text})]);st('update chaos_hot set n=n+1 where id=%s',[g])
 if k==0:st('rollback');st('select count(*) from chaos_ledger where id=%s',[i]);e=[[0]];f='rollback_mixed'
 else:
  if k==1:st('update chaos_ledger set n=n+cast(json_unquote(json_extract(j,\'$.x\')) as signed) where id=%s',[i]);a*=2;f='json_update_commit'
  elif k==2:st('replace into chaos_ledger(id,n,body,j) values(%s,%s,%s,%s)',[i,a,text+'replaced',json.dumps({'x':a})]);f='replace_commit'
  elif k==3:st('update chaos_ledger set n=n+coalesce((select sum(val) from seed where grp=%s),0) where id=%s',[g,i]);a+=sum(r[2] for r in seed if r[1]==g);f='subquery_commit'
  else:st('select count(*),sum(val) from seed where id between %s and %s',[j%150+1,j%150+50]);f='read_write_commit'
  st('commit');st('select id,n from chaos_ledger where id=%s',[i]);e=[[i,a]]
 add('chaos_mixed','mixed.'+f,None,expected=e,steps=steps,meta={'ledger_id':i,'final_n':None if k==0 else a,'hot_id':g})
def faults(j):
 if j<3000:
  n=R.randint(1,200);s='select sum(a.val+b.val+c.val) from seed a join seed b on a.grp=b.grp cross join seed c where c.id<=%s';add('chaos_faults','fault.cancel_query',s,[n],policy='cancel',meta={'delay_ms':1+j%19,'repeat':j//200,'row_limit':n})
 else:
  i=j+20000;a=R.randint(-10**12,10**12);add('chaos_faults','fault.disconnect_transaction','insert into chaos_aborted values(%s,%s)',[i,a],expected=[[0]],policy='disconnect',meta={'ledger_id':i})
fill('chaos_complex',15000,complex);fill('chaos_search',10000,search);fill('chaos_boundaries',10000,boundary);fill('chaos_mixed',10000,mixed);fill('chaos_faults',4995,faults)
for j in range(5):add('chaos_restart','fault.kill_restart','select 1',expected=[[1]],policy='restart',meta={'round':j+1,'concurrency':[16,32,64,96,128][j]})
assert len(cases)==50000 and len(seen)==50000
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n')
(P/'coverage.json').write_text(json.dumps({'total':len(cases),'unique_cases':len(seen),'modules':collections.Counter(c['module'] for c in cases),'families':collections.Counter(c['family'] for c in cases),'family_count':len({c['family'] for c in cases}),'policies':collections.Counter(c['oracle_policy'] for c in cases)},ensure_ascii=False,indent=2))
