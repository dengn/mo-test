import json,hashlib,random,math,collections,datetime
from pathlib import Path
P=Path(__file__).resolve().parent;R=random.Random(20261010200000);M=json.loads((P/'source-manifest.json').read_text());seen=set();cases=[];counts=collections.Counter();maps={}
BASE=1704067200
EVENTS=[(i,i%20,BASE+(i//20)*60+(i%7)*3,i*3-1000,None if i%13==0 else i%11,(i//50)%3,i%7) for i in range(1,2001)]
PAT=['alpha beta fox','alpha gamma dog','beta gamma fox','alpha beta gamma rabbit','omega gamma cat','omega beta dog']
def vv(i):return [((i*17+k*11)%101-50)/10 for k in range(3)]
def ww(i):return [((i*7+k*19)%97-48)/8 for k in range(3)]
ITEMS=[(i,i%17,json.dumps({'price':i*7,'color':['red','blue','green'][i%3],'tags':[i%5,i%7]}),json.dumps(vv(i)),json.dumps(ww(i)),'tok'+str(i)+' '+PAT[i%6]) for i in range(1,501)]
def src(e,needle):
 hit=[m for m in M if m['engine']==e and needle.lower() in m['path'].lower()]
 if not hit:raise ValueError((e,needle))
 return hit[0]['source_id']
def add(e,f,s,p=None,w=None,diff=True,steps=None,source=None,strategy='SQL rewrite',meta=None):
 st=steps or [{'sql':s,'params':p or []}];h=hashlib.sha256(json.dumps(st,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 if h in seen:return False
 seen.add(h);counts[e]+=1;key=e+'.'+f;maps[key]={'engine':e,'scenario':f,'source':source,'matrixone_strategy':strategy};cases.append(dict(id=f'X{len(cases)+1:06d}',module=e,family=key,statements=st,expected=w,mysql_differential=diff,expect_error=False,compare_mode='ordered',tolerance=2e-5 if not diff else 1e-6,sources=[source],sql_sha256=h,implementation=strategy,meta=meta));return True

def params():
 lo=R.randint(1,1800);hi=R.randint(lo,min(2000,lo+300));dev=R.randint(0,19);a=R.randint(-10000,10000);span=R.randint(60,3600);return lo,hi,dev,a,span

def mutation(e,j,partial=False):
 i=(['doris','starrocks','tidb','clickhouse','tdengine','milvus'].index(e)+1)*1000000+len(cases);a=R.randint(-10**10,10**10);name=e+'-'+str(j);st=[{'sql':'insert into cross_entities values(%s,%s,%s,%s)','params':[i,a,name,json.dumps({'n':a})]}]
 if partial:st.append({'sql':'update cross_entities set n=%s where id=%s','params':[a+7,i]});w=[[i,a+7,name]];f='partial_update'
 else:st.append({'sql':'insert into cross_entities values(%s,%s,%s,%s) on duplicate key update n=values(n),name=values(name),j=values(j)','params':[i,a+13,name+'new',json.dumps({'n':a+13})]});w=[[i,a+13,name+'new']];f='upsert_latest'
 st.append({'sql':'select id,n,name from cross_entities where id=%s','params':[i]})
 needle={'doris':'unique.md','starrocks':'primary_key_table.md','tidb':'transaction','clickhouse':'primary_key','tdengine':'schemaless','milvus':'upsert-entities.md'}[e]
 add(e,f,None,w=w,steps=st,source=src(e,needle),strategy='PRIMARY KEY plus explicit UPDATE / INSERT ON DUPLICATE KEY UPDATE',meta={'entity_id':i})
def analytics(e,j):
 lo,hi,dev,a,span=params();k=j%14;allrows=[r for r in EVENTS if lo<=r[0]<=hi];s=p=w=f=None
 if k==0:
  s='select device,count(*),sum(val),min(val),max(val) from cross_events where id between %s and %s group by device order by device';p=[lo,hi];f='multidimensional_aggregation';needle={'doris':'aggregate.md','starrocks':'aggregate_table.md','tidb':'aggregate-group-by','clickhouse':'aggregation','tdengine':'query-and-aggregate'}[e]
 elif k==1:
  s='select id,val,lag(val,1) over(partition by device order by epoch,id),lead(val,1) over(partition by device order by epoch,id) from cross_events where id between %s and %s order by id';p=[lo,hi];f='lag_lead_timeseries';needle={'doris':'window-function','starrocks':'Window_function','tidb':'window-functions','clickhouse':'window-functions/index','tdengine':'window-function'}[e]
 elif k==2:
  s='select id,device,val,sum(val) over(partition by device order by epoch,id rows between 2 preceding and current row) from cross_events where id between %s and %s order by id';p=[lo,hi];f='moving_sum';needle={'doris':'window-function','starrocks':'Window_function','tidb':'window-functions','clickhouse':'window-functions/index','tdengine':'window-function'}[e]
 elif k==3:
  s='select e.id,(select max(q.epoch) from cross_events q where q.device=e.device and q.epoch<=e.epoch-%s) from cross_events e where id between %s and %s order by id';p=[span,lo,hi];f='asof_preceding_match';needle={'doris':'asof-join','starrocks':'partitioning','tidb':'explain-joins','clickhouse':'joining-tables','tdengine':'05-join'}[e]
 elif k==4:
  s='select device,floor((epoch-%s)/%s) bucket,count(*),sum(val) from cross_events where id between %s and %s group by device,bucket order by device,bucket';p=[BASE,span,lo,hi];f='time_bucket_downsample';needle={'doris':'partitioning','starrocks':'partitioning','tidb':'partition-pruning','clickhouse':'time-series','tdengine':'distinguished'}[e]
 elif k==5:
  s='select device,sum(case when val>%s then val else 0 end),count(case when nullable is not null then 1 end),count(distinct category) from cross_events where id between %s and %s group by device order by device';p=[a,lo,hi];f='conditional_aggregate_exact_distinct';needle={'doris':'aggregate.md','starrocks':'aggregate_table.md','tidb':'aggregate-group-by','clickhouse':'avgIf','tdengine':'query-and-aggregate'}[e]
 elif k==6:
  s='with a as(select device,max(epoch) z from cross_events where id between %s and %s group by device) select e.id,e.device,e.val from cross_events e join a on e.device=a.device and e.epoch=a.z order by e.id';p=[lo,hi];f='latest_row_per_device';needle={'doris':'unique.md','starrocks':'primary_key_table','tidb':'derive-topn','clickhouse':'primary_key','tdengine':'distinguished'}[e]
 elif k==7:
  s='select e.device,sum(e.val),d.region from cross_events e join cross_devices d on e.device=d.id where e.id between %s and %s and d.region=%s group by e.device,d.region order by e.device';p=[lo,hi,dev%4];f='fact_dimension_tag_join';needle={'doris':'query-data/join','starrocks':'Lateral_join','tidb':'explain-joins','clickhouse':'joining-tables','tdengine':'05-join'}[e]
 elif k==8:
  s='select id,cast(json_unquote(json_extract(payload,\'$.price\')) as signed) p from cross_items where id between %s and %s and json_unquote(json_extract(payload,\'$.color\'))=%s order by id';p=[lo%400+1,lo%400+80,['red','blue','green'][dev%3]];f='json_metadata_filter';needle={'doris':'complex-types/json','starrocks':'Flat_json','tidb':'data-type-json','clickhouse':'json_type','tdengine':'schemaless'}[e]
 elif k==9:
  s='select i.id,t.tag from cross_items i join cross_tags t on i.id=t.item_id where i.id between %s and %s and t.tag=%s order by i.id,t.tag,t.pos';p=[lo%400+1,lo%400+80,dev%7];f='array_unnest_mapping';needle={'doris':'complex-types/array','starrocks':'unnest.md','tidb':'data-type-json','clickhouse':'working_with_arrays','tdengine':'schemaless'}[e]
 elif k==10:
  s='with a as(select id,device,state,epoch,lag(epoch) over(partition by device order by epoch,id) previous from cross_events where id between %s and %s),b as(select *,case when previous is null or epoch-previous>%s then 1 else 0 end new_session from a) select id,device,sum(new_session) over(partition by device order by epoch,id rows unbounded preceding) from b order by id';p=[lo,hi,span];f='session_window_emulation';needle={'doris':'window-function','starrocks':'Window_function','tidb':'window-functions','clickhouse':'window-functions/index','tdengine':'distinguished'}[e]
 elif k==11:
  s='select a.device,count(*) from cross_events a join cross_events b on a.device=b.device and b.epoch>a.epoch and b.epoch<=a.epoch+%s where a.state=0 and b.state=1 and a.id between %s and %s group by a.device order by a.device';p=[span,lo,hi];f='event_funnel_pair_count';needle={'doris':'window-function','starrocks':'window_funnel','tidb':'explain-joins','clickhouse':'joining-tables','tdengine':'distinguished'}[e]
 elif k==12:
  s='select id,val,case when nullable is null then cast(val as decimal(24,4)) else cast(nullable as decimal(24,4)) end from cross_events where epoch between %s and %s and device=%s order by id';p=[BASE+lo*2,BASE+hi*3,dev];f='time_partition_predicate_null';needle={'doris':'partitioning','starrocks':'partitioning','tidb':'partition-pruning','clickhouse':'partitioning_keys','tdengine':'query-and-aggregate'}[e]
 else:return mutation(e,j,partial=(j%28==13))
 if s is not None:add(e,f,s,p,w,source=src(e,needle),strategy='SQL rewrite; query-level semantic check, no physical-engine equivalence')
def milvus(j,e='milvus'):
 k=j%15
 if k==14:return mutation(e,j,partial=j%30==14)
 lo=R.randint(1,400);hi=R.randint(lo,min(500,lo+100));g=R.randint(0,16);n=R.randint(1,20);q=[R.randint(-1000,1000)/128 for _ in range(3)];p=json.dumps(q);word=R.choice(['alpha','beta','gamma','omega','fox','dog']);ids=list(range(lo,hi+1));metric='l2_distance';d=lambda i:math.sqrt(sum((x-y)**2 for x,y in zip(vv(i),q)));srcname='single-vector-search';f=None
 if k==0:f='dense_l2_topk';wanted=sorted(ids,key=lambda i:(round(d(i),3),i))[:n];s=f'select id,l2_distance(v,%s) z from cross_items where id between %s and %s order by round(z,3),id limit {n}';ps=[p,lo,hi];w=[[i,d(i)] for i in wanted]
 elif k==1:
  f='cosine_topk';normq=math.sqrt(sum(x*x for x in q));cd=lambda i:1-sum(x*y for x,y in zip(vv(i),q))/(math.sqrt(sum(x*x for x in vv(i)))*normq);wanted=sorted(ids,key=lambda i:(round(cd(i),3),i))[:n];s=f'select id,cosine_distance(v,%s) z from cross_items where id between %s and %s order by round(z,3),id limit {n}';ps=[p,lo,hi];w=[[i,cd(i)] for i in wanted]
 elif k==2:
  f='inner_product_topk';ip=lambda i:-sum(x*y for x,y in zip(vv(i),q));wanted=sorted(ids,key=lambda i:(round(ip(i),3),i))[:n];s=f'select id,inner_product(v,%s) z from cross_items where id between %s and %s order by round(z,3),id limit {n}';ps=[p,lo,hi];w=[[i,ip(i)] for i in wanted]
 elif k==3:
  f='scalar_prefilter';ids=[i for i in ids if i%17==g];wanted=sorted(ids,key=lambda i:(round(d(i),3),i))[:n];s=f'select id,l2_distance(v,%s) z from cross_items where id between %s and %s and grp=%s order by round(z,3),id limit {n}';ps=[p,lo,hi,g];w=[[i,d(i)] for i in wanted];srcname='filter'
 elif k==4:
  f='json_prefilter';color=['red','blue','green'][g%3];ids=[i for i in ids if i%3==g%3];wanted=sorted(ids,key=lambda i:(round(d(i),3),i))[:n];s=f'select id,l2_distance(v,%s) z from cross_items where id between %s and %s and json_unquote(json_extract(payload,\'$.color\'))=%s order by round(z,3),id limit {n}';ps=[p,lo,hi,color];w=[[i,d(i)] for i in wanted];srcname='json-indexing'
 elif k==5:
  f='range_search';radius=R.randint(1,150)/16;ids=[i for i in ids if d(i)<radius];s='select id from cross_items where id between %s and %s and l2_distance(v,%s)<%s order by id';ps=[lo,hi,p,radius];w=[[i] for i in ids];srcname='range-search'
 elif k==6:
  f='group_best_hit';best={}
  for i in ids:
   if i%17 not in best or (d(i),i)<(d(best[i%17]),best[i%17]):best[i%17]=i
  wanted=sorted(best.values(),key=lambda i:(round(d(i),3),i))[:n];s=f'with a as(select id,grp,l2_distance(v,%s) z from cross_items where id between %s and %s),b as(select *,row_number() over(partition by grp order by z,id) rn from a) select id,z from b where rn=1 order by round(z,3),id limit {n}';ps=[p,lo,hi];w=[[i,d(i)] for i in wanted];srcname='grouping-search'
 elif k==7:
  f='multi_vector_weighted';alpha=R.randint(1,99)/100;score=lambda i:alpha*d(i)+(1-alpha)*math.sqrt(sum((x-y)**2 for x,y in zip(ww(i),q)));wanted=sorted(ids,key=lambda i:(round(score(i),3),i))[:n];s=f'select id,%s*l2_distance(v,%s)+(1-%s)*l2_distance(w,%s) z from cross_items where id between %s and %s order by round(z,3),id limit {n}';ps=[alpha,p,alpha,p,lo,hi];w=[[i,score(i)] for i in wanted];srcname='multi-vector-search'
 elif k==8:
  f='hybrid_text_vector';ids=[i for i in ids if word in PAT[i%6].split()];wanted=sorted(ids,key=lambda i:(round(d(i),3),i))[:n];s=f'select id,l2_distance(v,%s) z from cross_items where match(body) against(%s in boolean mode) and id between %s and %s order by round(z,3),id limit {n}';ps=[p,word,lo,hi];w=[[i,d(i)] for i in wanted];srcname='hybrid_search_with_milvus'
 elif k==9:
  f='rrf_two_dense_ranks';order1=sorted(ids,key=lambda i:(round(d(i),3),i));d2=lambda i:math.sqrt(sum((x-y)**2 for x,y in zip(ww(i),q)));order2=sorted(ids,key=lambda i:(round(d2(i),3),i));r1={i:r+1 for r,i in enumerate(order1)};r2={i:r+1 for r,i in enumerate(order2)};rr=R.randint(20,100);score=lambda i:1/(rr+r1[i])+1/(rr+r2[i]);wanted=sorted(ids,key=lambda i:(-score(i),i))[:n];s=f'with a as(select id,row_number() over(order by round(l2_distance(v,%s),3),id) r1,row_number() over(order by round(l2_distance(w,%s),3),id) r2 from cross_items where id between %s and %s) select id,1e0/(%s+r1)+1e0/(%s+r2) z from a order by z desc,id limit {n}';ps=[p,p,lo,hi,rr,rr];w=[[i,score(i)] for i in wanted];srcname='multi-vector-search'
 elif k==10:f='fulltext_boolean_filter';s='select id from cross_items where match(body) against(%s in boolean mode) and id between %s and %s order by id';ps=['+'+word+' -omega',lo,hi];w=[[i] for i in ids if word in PAT[i%6].split() and 'omega' not in PAT[i%6].split()];srcname='full-text-search'
 elif k==11:f='array_tag_filter';tag=g%7;ids=[i for i in ids if tag in [i%5,i%7]];s='select id from cross_items where id between %s and %s and (cast(json_unquote(json_extract(payload,\'$.tags[0]\')) as signed)=%s or cast(json_unquote(json_extract(payload,\'$.tags[1]\')) as signed)=%s) order by id';ps=[lo,hi,tag,tag];w=[[i] for i in ids];srcname='array_data_type'
 elif k==12:f='nullable_scalar_aggregate';s='select count(nullable),sum(coalesce(nullable,0)) from cross_events where id between %s and %s';ps=[lo,hi];rr=[r for r in EVENTS if lo<=r[0]<=hi];w=[[sum(r[4] is not None for r in rr),sum(r[4] or 0 for r in rr)]];srcname='nullable-and-default'
 else:f='partition_key_filter';s='select id from cross_items where id between %s and %s and grp=%s order by id';ps=[lo,hi,g];w=[[i] for i in ids if i%17==g];srcname='use-partition-key'
 add(e,f,s,ps,w,diff=False,source=src(e,srcname if e=='milvus' else 'vector'),strategy='Exact SQL equivalent on vecf32 / scalar / FULLTEXT; ANN recall and cross-engine BM25 scores not asserted')
# Doris/StarRocks/TiDB/ClickHouse reuse a subset of vector scenarios through explicit SQL rewrites.
for index,e in enumerate(['doris','starrocks','tidb','clickhouse','tdengine','milvus']):
 target=16667 if index<4 else 16666;j=0
 while counts[e]<target:
  if e=='milvus':milvus(j)
  elif e!='tdengine' and j%5==0:milvus(j//5,e)
  else:analytics(e,j)
  j+=1
 print(e,counts[e],flush=True)
assert len(cases)==100000 and len(seen)==100000
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n')
(P/'fixtures.json').write_text(json.dumps({'events':EVENTS,'items':ITEMS,'devices':[(i,i%4,'device'+str(i)) for i in range(20)],'tags':[(i,pos,t) for i in range(1,501) for pos,t in enumerate([i%5,i%7])]},ensure_ascii=False))
(P/'mapping.json').write_text(json.dumps(maps,ensure_ascii=False,indent=2))
(P/'coverage.json').write_text(json.dumps({'total':len(cases),'unique_sql_and_parameters':len(seen),'engines':counts,'families':collections.Counter(c['family'] for c in cases),'family_count':len(maps),'mysql_differential':sum(c['mysql_differential'] for c in cases),'source_count':len(M)},ensure_ascii=False,indent=2))
