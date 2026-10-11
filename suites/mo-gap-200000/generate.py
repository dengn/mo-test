import json,random,hashlib,math,collections,datetime
from pathlib import Path
P=Path(__file__).resolve().parent;R=random.Random(50000020261010);seen=set();cases=[];counts=collections.Counter();sources=[]
repo=Path('/workspace/matrixone-latest');commit='2726fb419b3afa1db2686ae1b2aaca563d1ae214'
for path in ['test/distributed/cases/vector/vector_func.sql','test/distributed/cases/vector/vector_type.sql','test/distributed/cases/stage/export_format.sql']:
 data=(repo/path).read_bytes();sources.append(dict(source_id='matrixorigin/matrixone:'+path,commit=commit,path=path,sha256=hashlib.sha256(data).hexdigest(),url=f'https://github.com/matrixorigin/matrixone/blob/{commit}/{path}'))
for x in repo.glob('test/distributed/cases/**/*.sql'):
 if any(t in x.name.lower() for t in ['foreign','check','window','union','constraint']) and len(sources)<28:
  data=x.read_bytes();path=str(x.relative_to(repo));sources.append(dict(source_id='matrixorigin/matrixone:'+path,commit=commit,path=path,sha256=hashlib.sha256(data).hexdigest(),url=f'https://github.com/matrixorigin/matrixone/blob/{commit}/{path}'))
(P/'source-manifest.json').write_text(json.dumps(sources,indent=2))
def source(kind):
 hit=[x['source_id'] for x in sources if kind in x['path']];return hit[:2] or [sources[0]['source_id']]
def add(module,f,s,p=None,w=None,diff=True,policy='normal',steps=None,meta=None,mode='ordered',tol=1e-6):
 st=steps or [{'sql':s,'params':p or []}];canonical={'statements':st,'policy':policy,'meta':meta};h=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 if h in seen:return
 seen.add(h);counts[module]+=1;cases.append(dict(id=f'G{len(cases)+1:06d}',module=module,family=module+'.'+f,statements=st,expected=w,mysql_differential=diff,expect_error=False,compare_mode=mode,tolerance=tol,sources=source('vector' if module=='search_edges' else 'window' if module=='windows_sets' else 'foreign' if module=='constraints' else 'union'),sql_sha256=h,oracle_policy=policy,meta=meta))
def fill(mod,n,fn):
 j=0
 while counts[mod]<n:fn(j);j+=1
 print(mod,n,flush=True)
def constraints(j):
 a=R.randint(-10**8,10**8);b='tag'+str(j);k=j%10;t='{table}';st=[]
 def step(s,p=None,reject=False):st.append({'sql':s,'params':p or [],'must_reject':reject})
 if k in [0,1,2,3]:
  step(f'create table {t}(id bigint primary key,n bigint not null,tag varchar(100),unique key uq(tag))');step(f'insert into {t} values(1,%s,%s)',[a,b])
  if k==0:step(f'insert into {t} values(1,%s,%s)',[a+1,b+'new'],True);f='primary_key_reject'
  elif k==1:step(f'insert into {t} values(2,%s,%s)',[a+1,b],True);f='unique_reject'
  elif k==2:step(f'insert into {t} values(2,null,%s)',[b+'new'],True);f='not_null_reject'
  else:step(f'insert into {t} values(2,%s,null),(3,%s,null)',[a+1,a+2]);f='unique_nulls'
  step(f'select id,n from {t} order by id');w=[[1,a],[2,a+1],[3,a+2]] if k==3 else [[1,a]]
 elif k in [4,5,6]:
  action='cascade' if k==4 else 'restrict' if k==5 else 'set null';step(f'create table {t}_p(id bigint primary key,n bigint)');step(f'create table {t}(id bigint primary key,pid bigint,n bigint,foreign key(pid) references {t}_p(id) on delete {action})');step(f'insert into {t}_p values(1,%s)',[a]);step(f'insert into {t} values(1,1,%s)',[a])
  step(f'delete from {t}_p where id=1',reject=k==5);step(f'select id,pid,n from {t} order by id');w=[] if k==4 else [[1,None if k==6 else 1,a]];f='fk_delete_'+action.replace(' ','_')
 elif k==7:
  step(f'create table {t}(id bigint primary key,n bigint check(n>={a} and n<{a+100}))');step(f'insert into {t} values(1,%s)',[a+1]);step(f'insert into {t} values(2,%s)',[a-1],True);step(f'select id,n from {t} order by id');w=[[1,a+1]];f='check_enforcement'
 elif k==8:
  step(f'create table {t}(id bigint primary key,n decimal(8,2))');step(f'insert into {t} values(1,%s)',[str(a/100)]);step(f'select id,n from {t}');w=None;f='decimal_insert_bounds'
 else:
  step(f'create table {t}(id bigint primary key,n bigint)');step(f'insert into {t} values(1,%s)',[a]);step(f'create view {t}_v as select id,n*2 z from {t} where n={a}');step(f'select * from {t}_v');w=[[1,a*2]];f='view_expression'
 add('constraints',f,None,w=w,steps=st,policy='constraint',meta={'table_cleanup':True})
def joins(j):
 lo=R.randint(1,1800);hi=R.randint(lo,min(2000,lo+250));n=R.randint(-10000,10000);d=R.randint(0,19);k=j%18
 Q=[
 ('full_outer_emulated','select a.id,b.id from cross_events a left join cross_events b on b.id=a.id+%s where a.id between %s and %s union all select a.id,b.id from cross_events b left join cross_events a on b.id=a.id+%s where a.id is null and b.id between %s and %s order by 1,2',[d+1,lo,hi,d+1,lo,hi]),
 ('anti_join','select a.id from cross_events a where a.id between %s and %s and not exists(select 1 from cross_events b where b.device=a.device and b.val>%s) order by a.id',[lo,hi,n]),
 ('semi_join','select a.id from cross_events a where a.id between %s and %s and exists(select 1 from cross_events b where b.device=a.device and b.val>%s) order by a.id',[lo,hi,n]),
 ('nested_cte','with a as(select * from cross_events where id between %s and %s),b as(select device,sum(val) z from a group by device),c as(select device,z,rank() over(order by z desc) rn from b) select * from c where z>%s order by device',[lo,hi,n]),
 ('non_equi_join','select a.id,count(b.id) from cross_events a left join cross_events b on b.device=a.device and b.epoch between a.epoch-%s and a.epoch+%s where a.id between %s and %s group by a.id order by a.id',[d*60,d*60,lo,hi]),
 ('union_null_types','select id,cast(val as decimal(22,3)) z from cross_events where id between %s and %s union all select id,cast(null as decimal(22,3)) from cross_events where device=%s order by id,z',[lo,hi,d]),
 ('distinct_null_join','select distinct a.nullable,b.category from cross_events a join cross_events b on b.id=a.id+%s where a.id between %s and %s order by a.nullable,b.category',[d+1,lo,hi]),
 ('correlated_aggregate_case','select a.id,case when a.nullable is null then (select max(b.val) from cross_events b where b.device=a.device) else a.val end from cross_events a where id between %s and %s order by id',[lo,hi]),
 ('recursive_cte','with recursive c(n) as(select 1 union all select n+1 from c where n<%s) select count(*),sum(n) from c',[j%127+1]),
 ('limit_nested_offset','select * from(select id,val from cross_events where id between %s and %s order by id limit %s offset %s) a order by id desc',[lo,hi,d+1,j%17]),
 ('group_concat_order','select device,group_concat(cast(id as char) order by id separator %s) from cross_events where id between %s and %s group by device order by device',['|'+str(j%31)+'|',lo,hi]),
 ('variance_stddev','select device,var_pop(val),stddev_pop(val),var_samp(val) from cross_events where id between %s and %s group by device order by device',[lo,hi]),
 ('json_subquery','select id,json_unquote(json_extract(json_object(\'n\',(select max(val) from cross_events b where b.device=a.device)),\'$.n\')) from cross_events a where id between %s and %s order by id',[lo,hi]),
 ('having_double_nested','select device,sum(val) z from cross_events where id between %s and %s group by device having sum(val)>(select coalesce(avg(val),0) from cross_events where device=%s) order by device',[lo,hi,d]),
 ('cross_join_empty','select count(*) from cross_events a cross join(select id from cross_events where id>%s and id<%s)b where a.id between %s and %s',[hi,lo,lo,hi]),
 ('boolean_null_case','select id from cross_events where id between %s and %s and ((nullable is null and val>%s) or (nullable is not null and device=%s)) order by id',[lo,hi,n,d]),
 ('join_three_relations','select e.id,d.region,r.ntext from cross_events e join cross_devices d on e.device=d.id left join etl_raw r on r.id=e.id where e.id between %s and %s and d.region=%s order by e.id',[lo,hi,d%4]),
 ('cte_multiple_consumers','with a as(select device,val from cross_events where id between %s and %s) select (select count(*) from a),(select sum(val) from a),(select count(distinct device) from a)',[lo,hi])]
 f,s,p=Q[k];add('joins_ctes',f,s,p)
def windows(j):
 lo=R.randint(1,1800);hi=R.randint(lo,min(2000,lo+250));offset=R.randint(0,8);k=j%20
 if k<12:
  fs=['row_number()','rank()','dense_rank()',f'ntile({1+j%31})','percent_rank()','cume_dist()','first_value(val)','last_value(val)',f'nth_value(val,{1+j%15})',f'lag(val,{offset},{j})',f'lead(val,{offset},{j})','sum(val)'][k]
  frame=f'rows between {offset} preceding and {j%7} following' if k>=6 else '';s=f'select id,{fs} over(partition by device order by epoch,id {frame}) from cross_events where id between %s and %s order by id';p=[lo,hi];f='analytic_'+str(k)
 elif k<16:
  agg=['sum(val)','avg(val)','count(nullable)','max(val)'][k-12];s=f'select id,{agg} over(partition by device order by epoch range between {offset*60} preceding and {j%7*60} following) from cross_events where id between %s and %s order by id';p=[lo,hi];f='range_'+str(k)
 elif k==16:s='select id from cross_events where id between %s and %s intersect select id from cross_events where device=%s order by id';p=[lo,hi,j%20];f='intersect'
 elif k==17:s='select id from cross_events where id between %s and %s except select id from cross_events where device=%s order by id';p=[lo,hi,j%20];f='except'
 elif k==18:s='select id from cross_events where id between %s and %s union select id from cross_events where id between %s and %s order by id';p=[lo,hi,max(1,lo-offset),hi+offset];f='union_distinct'
 else:s='select id from cross_events where id between %s and %s union all select id from cross_events where id between %s and %s order by id';p=[lo,hi,max(1,lo-offset),hi+offset];f='union_all'
 add('windows_sets',f,s,p)
def types(j):
 a=R.randint(-10**12,10**12);b=R.randint(1,100000);s=R.choice(['中文😀','alpha','café','a,b','a\nb',' apostrophe\' '])+str(j);k=j%25;d=datetime.date(2000,1,1)+datetime.timedelta(days=j%15000)
 Q=[('mixed_numeric_case','select case when %s<0 then cast(%s as decimal(38,10)) else cast(%s as double) end',[a,str(a/100),str(a/100)]),('decimal_scale','select cast(%s as decimal(38,15))*cast(%s as decimal(38,15))',[str(a/100000),str(b/100000)]),('null_union','select cast(%s as char) z union all select null order by z',[a]),('utf8_regex','select %s regexp %s',[s,'[0-9]+$']),('regex_replace','select regexp_replace(%s,%s,%s)',[s,'[0-9]+','编号'+str(j)]),('regex_substr','select regexp_substr(%s,%s)',[s,'[0-9]+']),('json_numeric_cast','select cast(json_unquote(json_extract(%s,\'$.n\')) as decimal(38,5))',[json.dumps({'n':a})]),('boolean_arithmetic','select (%s>%s)+(%s is null),coalesce(null,%s)>0',[a,b,a,b]),('datetime_interval','select date_add(%s,interval %s second),date_sub(%s,interval %s month)',[str(d)+' 12:30:45',b,str(d),j%25]),('date_timezone','select convert_tz(%s,%s,%s)',[str(d)+' 12:30:45','+00:00',f'+{j%12:02d}:00']),('date_numeric_mysql','select dayofmonth(%s),yearweek(%s,3)',[int(d.strftime('%Y%m%d')),int(d.strftime('%Y%m%d'))]),('time_numeric_mysql','select second(%s),minute(%s),hour(%s)',[j%24*10000+j%60*100+j%60]*3),('time_clip','select maketime(%s,%s,%s)',[j%2000-1000,j%60,j%60]),('float_overflow','select exp(%s),power(10,%s)',[j%1000,j%400]),('round_precision_unsigned','select round(%s,%s),truncate(%s,%s)',[a,2**64-1-j%100,a,2**64-1-j%100]),('bit_shift_boundary','select %s << %s,%s >> %s',[abs(a),j%100,abs(a),j%100]),('binary_hex','select hex(unhex(%s)),length(unhex(%s))',[format(abs(a),'x'),format(abs(a),'x')]),('unicode_collate','select locate(%s,%s collate utf8mb4_bin),%s like %s',[s.upper(),s,s,s.upper()]),('concat_literal','select '+"'a"+str(j)+"' 'b"+str(j)+"'",[]),('negative_zero','select cast(%s as double)=0,cast(%s as decimal(20,10))',['-0.'+'0'*(j%8)+str(j%10),'-0.'+'0'*(j%8)+str(j%10)]),('decimal_overflow','select cast(%s as decimal(5,2))',[str(a)]),('json_depth','select json_valid(%s),json_extract(%s,\'$[0]\')',['['*(1+j%100)+str(a)+']'*(1+j%100)]*2),('string_binary_compare','select cast(%s as binary)=cast(%s as binary),strcmp(%s,%s)',[s,s.upper(),s,s.upper()]),('timestamp_roundtrip','select unix_timestamp(from_unixtime(%s)),from_unixtime(%s)',[1704067200+j*13]*2),('json_unicode_quote','select json_unquote(json_extract(json_object(\'x\',%s),\'$.x\'))',[s])]
 f,sql,p=Q[k];add('mixed_types',f,sql,p,tol=2e-5)
def search(j):
 k=j%15;dim=[8,32,64,128,256,512,768,1536][j%8];v=[R.randint(-100,100)/8 for _ in range(dim)];u=[R.randint(-100,100)/8 for _ in range(dim)];x=json.dumps(v);y=json.dumps(u);typ='vecf64' if j%2 else 'vecf32';L=f'cast(%s as {typ}({dim}))';lo=R.randint(1,150);hi=R.randint(lo,200)
 if k<9:
  expr=[f'l2_distance({L},{L})',f'l2_distance_sq({L},{L})',f'inner_product({L},{L})',f'l1_distance({L},{L})',f'l1_norm({L})',f'l2_norm({L})',f'cosine_distance({L},{L})',f'l2_norm(normalize_l2({L}))',f'vector_dims({L})'][k];s='select '+expr;p=[x] if k in [4,5,7,8] else [x,y]
  vals=[math.sqrt(sum((a-b)**2 for a,b in zip(v,u))),sum((a-b)**2 for a,b in zip(v,u)),-sum(a*b for a,b in zip(v,u)),sum(abs(a-b) for a,b in zip(v,u)),sum(abs(a) for a in v),math.sqrt(sum(a*a for a in v)),1-sum(a*b for a,b in zip(v,u))/math.sqrt(sum(a*a for a in v)*sum(b*b for b in u)),1,dim];w=[[vals[k]]];f='highdim_'+str(k);add('search_edges',f,s,p,w,diff=False,tol=2e-5);return
 if k==9:s=f'select l2_distance(cast(%s as vecf64(2)),cast(%s as vecf64(2)))';p=[f'[{j+1}e200,1e200]','[0,0]'];add('search_edges','finite_overflow',s,p,diff=False,policy='robustness');return
 if k==10:s=f'select subvector({L},%s,%s)';p=[x,-1-j%dim,1+j%dim];add('search_edges','subvector_bounds',s,p,diff=False,policy='robustness');return
 word=R.choice(['alpha','beta','gamma','omega','fox','dog']);table='ft2' if j%2 else 'ft';terms=[word+'*','+'+word+' -(fox dog)','"'+word+' beta" @'+str(1+j%10),'('+word+' beta) -omega'][k-11];s=f'select id from {table} where match(body) against(%s in boolean mode) and id between %s and %s order by id';p=[terms,lo,hi];add('search_edges','fulltext_grammar_'+str(k),s,p,diff=False,policy='robustness')
def fault(j):
 k=j%5;a=R.randint(-10**8,10**8)
 if k==0:add('concurrency','atomic_increment','update gap_atomic set n=n+1 where id=%s',[j+1],w=[[4]],diff=False,policy='atomic',meta={'row_id':j+1,'workers':4,'initial':a})
 elif k==1:add('concurrency','rollback_disconnect','insert into gap_aborted values(%s,%s)',[j+1,a],w=[[0]],diff=False,policy='disconnect',meta={'row_id':j+1})
 elif k==2:add('concurrency','cancel_complex','select sum(a.val+b.val+c.val) from cross_events a join cross_events b on a.device=b.device cross join cross_devices c where a.id between %s and %s',[j%1800+1,j%1800+50],diff=False,policy='cancel',meta={'delay_ms':1+j%23})
 elif k==3:add('concurrency','invalid_regex_survival','select regexp_replace(%s,%s,%s)',['中文😀'+str(j),'['*(j%100+1),str(a)],diff=False,policy='robustness')
 else:add('concurrency','wide_deep_expression','select '+('('* (1+j%128))+'%s'+(')'*(1+j%128)),[a],w=[[a]],diff=False)
fill('constraints',5000,constraints);fill('joins_ctes',45000,joins);fill('windows_sets',35000,windows);fill('mixed_types',50000,types);fill('search_edges',50000,search);fill('concurrency',15000,fault)
assert len(cases)==200000 and len(seen)==200000
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n')
(P/'coverage.json').write_text(json.dumps({'total':len(cases),'unique_case_definitions':len(seen),'modules':counts,'families':collections.Counter(c['family'] for c in cases),'family_count':len({c['family'] for c in cases}),'policies':collections.Counter(c['oracle_policy'] for c in cases)},ensure_ascii=False,indent=2))
