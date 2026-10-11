import json,hashlib,random,datetime,decimal,collections
from pathlib import Path
P=Path(__file__).resolve().parent;R=random.Random(30000020261010);M=[x for x in json.load(open(P/'source-manifest.json')) if x['status']=='downloaded'];cases=[];seen=set();counts=collections.Counter();maps={}
def src(engine,needle):
 hits=[x for x in M if x['engine']==engine and needle in x['url']]
 if not hits:raise ValueError((engine,needle))
 return hits[0]['source_id']
RAW=[(i,i%7,1704067200+i*13,i%23==0,str(i*7-2000),str((i*11-5000)/100),'中文😀,line '+str(i)+('\nsecond' if i%17==0 else ''),json.dumps({'n':i*7-2000,'s':'name'+str(i),'arr':[i%5,i%7],'extra':None if i%3 else i}),str(datetime.date(2020,1,1)+datetime.timedelta(days=i%1461))) for i in range(1,2001)]
def add(module,f,s,p=None,w=None,diff=True,policy='normal',steps=None,source=None,meta=None,strategy='SQL equivalent'):
 st=steps or [{'sql':s,'params':p or []}];core={'statements':st,'policy':policy,'meta':meta};h=hashlib.sha256(json.dumps(core,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 if h in seen:return
 seen.add(h);counts[module]+=1;key=module+'.'+f;maps[key]={'source':source,'implementation':strategy};cases.append(dict(id=f'E{len(cases)+1:06d}',module=module,family=key,statements=st,expected=w,mysql_differential=diff,expect_error=False,compare_mode='ordered',tolerance=1e-6,sources=[source],sql_sha256=h,oracle_policy=policy,meta=meta,implementation=strategy))
def fill(module,n,fn):
 j=0
 while counts[module]<n:fn(j);j+=1
 print(module,counts[module],flush=True)
def ingest(j):
 if j<1000:
  batch=j+1;rows=[[batch,k,k*7-j,'中文😀 row,'+str(j)+'-'+str(k),json.dumps({'n':k,'batch':batch})] for k in range(1,11+j%21)]
  add('ingest','native_csv_load','LOAD DATA INFILE {input} INTO TABLE etl_csv FIELDS TERMINATED BY \',\' ENCLOSED BY \'"\' LINES TERMINATED BY \'\\n\' IGNORE 1 LINES',w=rows,diff=False,policy='native_csv',source=src('snowflake','copy-into-table'),meta={'batch':batch,'rows':rows},strategy='Server LOAD DATA INFILE on real local CSV; independent Python CSV oracle');return
 k=j%8;i=j+100000;n=R.randint(-10**12,10**12);s=R.choice(['中文😀','apostrophe\'quote','comma,value','line\nsecond',' leading trailing ','','NULL','0'])+'-'+str(j);doc=json.dumps({'n':n,'s':s,'v':None if j%3 else j})
 steps=[{'sql':'insert into etl_ingest values(%s,%s,%s,%s)','params':[i,str(n),s,doc]}]
 if k==0:q='select cast(ntext as signed),body from etl_ingest where id=%s';w=[[n,s]];f='varchar_numeric_unicode'
 elif k==1:q='select json_unquote(json_extract(meta,\'$.s\')),cast(json_unquote(json_extract(meta,\'$.n\')) as signed) from etl_ingest where id=%s';w=[[s,n]];f='json_payload_types'
 elif k==2:q='select length(body),char_length(body) from etl_ingest where id=%s';w=[[len(s.encode()),len(s)]];f='utf8_encoding'
 elif k==3:q='select concat_ws(\'|\',body,ntext) from etl_ingest where id=%s';w=[[s+'|'+str(n)]];f='quoted_delimiters'
 elif k==4:q='select json_extract(meta,\'$.missing\') is null,json_unquote(json_extract(meta,\'$.s\')) from etl_ingest where id=%s';w=[[1,s]];f='missing_fields'
 elif k==5:q='select id,cast(ntext as decimal(25,4)) from etl_ingest where id=%s';w=None;f='decimal_precision'
 elif k==6:q='select body,body is null from etl_ingest where id=%s';w=[[s,0]];f='null_literal_preserved'
 else:q='select body,cast(json_unquote(json_extract(meta,\'$.n\')) as signed)=cast(ntext as signed) from etl_ingest where id=%s';w=[[s,1]];f='typed_batch_consistency'
 steps.append({'sql':q,'params':[i]});add('ingest',f,None,w=w,steps=steps,source=src('fivetran','databases/mysql'),meta={'insert_id':i},strategy='Parameterized batch ingest of connector-shaped records; no live Fivetran connector')
def transform(j):
 lo=R.randint(1,1900);hi=R.randint(lo,min(2000,lo+200));g=R.randint(0,6);v=R.randint(-10000,10000);k=j%20
 qq=[
 ('staging_cast','select id,cast(ntext as signed),cast(amount as decimal(20,4)) from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('delete_filter','select id from etl_raw where id between %s and %s and not _fivetran_deleted order by id',[lo,hi]),
 ('json_flatten','select id,cast(json_unquote(json_extract(meta,\'$.n\')) as signed),json_unquote(json_extract(meta,\'$.s\')) from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('json_array_to_rows','select id,0 pos,json_extract(meta,\'$.arr[0]\') from etl_raw where id between %s and %s union all select id,1,json_extract(meta,\'$.arr[1]\') from etl_raw where id between %s and %s order by id,pos',[lo,hi,lo,hi]),
 ('date_normalization','select id,date_format(str_to_date(event_date,\'%%Y-%%m-%%d\'),\'%%Y%%m%%d\') from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('null_handling','select id,coalesce(json_unquote(json_extract(meta,\'$.missing\')),body),nullif(ntext,%s) from etl_raw where id between %s and %s order by id',[str(v),lo,hi]),
 ('dimension_join','select r.id,r.source_id,d.region from etl_raw r join cross_devices d on r.source_id=d.id where r.id between %s and %s and d.region=%s order by r.id',[lo,hi,g%4]),
 ('warehouse_aggregate','select source_id,count(*),sum(cast(amount as decimal(20,4))),count(distinct body) from etl_raw where id between %s and %s group by source_id order by source_id',[lo,hi]),
 ('qualify_rewrite','with a as(select id,source_id,row_number() over(partition by source_id order by _fivetran_synced desc,id desc) rn from etl_raw where id between %s and %s) select id,source_id from a where rn=1 order by source_id',[lo,hi]),
 ('not_null_test','select count(*) from etl_raw where id between %s and %s and ntext is null',[lo,hi]),
 ('unique_test','select id,count(*) from etl_raw where id between %s and %s group by id having count(*)>1 order by id',[lo,hi]),
 ('accepted_values_test','select id from etl_raw where id between %s and %s and source_id not in(0,1,2,3,4,5,6) order by id',[lo,hi]),
 ('relationships_test','select r.id from etl_raw r left join cross_devices d on r.source_id=d.id where r.id between %s and %s and d.id is null order by r.id',[lo,hi]),
 ('watermark_predicate','select id from etl_raw where id between %s and %s and _fivetran_synced>%s order by id',[lo,hi,1704067200+g*2500]),
 ('incremental_model_query','with a as(select id,cast(ntext as signed) n from etl_raw where id between %s and %s and _fivetran_synced>%s) select id,n*2 from a order by id',[lo,hi,1704067200+g*2500]),
 ('row_hash','select id,md5(concat_ws(\'|\',cast(id as char),ntext,body)) from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('whitespace_cleaning','select id,trim(body),replace(body,\'\\n\',\' \') from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('schema_drift_json','select id,json_extract(meta,\'$.extra\') is null,json_extract(meta,\'$.absent\') is null from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('moving_model','select id,sum(cast(ntext as signed)) over(partition by source_id order by id rows between 3 preceding and current row) from etl_raw where id between %s and %s order by id',[lo,hi]),
 ('full_refresh_equivalence','select source_id,count(*),coalesce(sum(cast(ntext as signed)),0) from etl_raw where id between %s and %s and _fivetran_deleted=0 group by source_id order by source_id',[lo,hi])]
 f,s,p=qq[k];source=src('dbt','data-tests') if 9<=k<=12 else (src('snowflake','data-load-transform') if k<=5 else src('dbt','sql-models'));add('transform',f,s,p,source=source)
def incremental(j):
 i=j+1;n=R.randint(-10**9,10**9);seq=R.randint(10,10000);k=j%10;steps=[]
 def st(s,p=None):steps.append({'sql':s,'params':p or []})
 st('insert into etl_target values(%s,%s,%s,0,%s,%s)',[i,n,seq,1704067200+j,'row'+str(i)])
 def up(value,version,deleted=0):st('insert into etl_target values(%s,%s,%s,%s,%s,%s) on duplicate key update n=if(values(seq)>=seq,values(n),n),deleted=if(values(seq)>=seq,values(deleted),deleted),seq=greatest(seq,values(seq))',[i,value,version,deleted,1704067200+j,'row'+str(i)])
 if k==0:up(n+7,seq+1);up(n+7,seq+1);w=[[i,n+7,seq+1,0]];f='duplicate_delivery_idempotent'
 elif k==1:up(n+9,seq+2);up(n-5,seq-1);w=[[i,n+9,seq+2,0]];f='out_of_order_lww'
 elif k==2:up(n,seq+1,1);w=[[i,n,seq+1,1]];f='soft_delete_propagation'
 elif k==3:st('delete from etl_target where id=%s',[i]);st('select count(*) from etl_target where id=%s',[i]);w=[[0]];f='hard_delete_propagation'
 elif k==4:up(n,seq+1,1);up(n+11,seq+2,0);w=[[i,n+11,seq+2,0]];f='resurrection'
 elif k==5:st('begin');st('update etl_target set n=%s where id=%s',[n+3,i]);st('rollback');w=[[i,n,seq,0]];f='failed_batch_rollback'
 elif k==6:st('begin');st('update etl_target set n=%s,seq=%s where id=%s',[n+13,seq+1,i]);st('commit');w=[[i,n+13,seq+1,0]];f='atomic_batch_commit'
 elif k==7:up(n+17,seq+10);up(n+15,seq+8);w=[[i,n+17,seq+10,0]];f='watermark_gap'
 elif k==8:up(n,seq);up(n,seq);w=[[i,n,seq,0]];f='retry_unchanged'
 else:st('update etl_target set body=concat(body,%s) where id=%s',['-partial',i]);w=[[i,n,seq,0]];f='partial_update_preserves_columns'
 if k!=3:st('select id,n,seq,deleted from etl_target where id=%s',[i])
 add('incremental',f,None,w=w,steps=steps,source=src('dbt','incremental-models') if k in [0,1,5,6,7,8] else src('fivetran','databases/mysql'),meta={'entity_id':i},strategy='Explicit SQL LWW watermark and transaction policy; no vendor MERGE syntax assumed')
def snapshot(j):
 i=j+1;n=R.randint(-10**10,10**10);start=R.randint(100,100000);end=start+R.randint(1,100);k=j%5;st=[{'sql':'insert into etl_history values(%s,%s,null,%s,0)','params':[i,start,n]}]
 if k!=1:
  st+=[{'sql':'begin'},{'sql':'update etl_history set valid_to=%s where key_id=%s and valid_to is null','params':[end,i]},{'sql':'insert into etl_history values(%s,%s,null,%s,%s)','params':[i,end,n+1,1 if k==2 else 0]},{'sql':'commit'}]
 if k==0:s='select valid_from,valid_to,n,deleted from etl_history where key_id=%s order by valid_from';p=[i];w=[[start,end,n,0],[end,None,n+1,0]];f='scd2_change'
 elif k==1:s='select count(*),max(n) from etl_history where key_id=%s';p=[i];w=[[1,n]];f='snapshot_unchanged'
 elif k==2:s='select n,deleted from etl_history where key_id=%s and valid_to is null';p=[i];w=[[n+1,1]];f='snapshot_delete'
 elif k==3:s='select n from etl_history where key_id=%s and valid_from<=%s and (valid_to is null or valid_to>%s)';p=[i,start,start];w=[[n]];f='point_in_time'
 else:s='select count(*) from etl_history a join etl_history b on a.key_id=b.key_id and a.valid_from<b.valid_from and (a.valid_to is null or a.valid_to>b.valid_from) where a.key_id=%s';p=[i];w=[[0]];f='no_overlapping_validity'
 st.append({'sql':s,'params':p});add('snapshot',f,None,w=w,steps=st,source=src('dbt','snapshots'),meta={'key_id':i},strategy='SCD2 history SQL matching dbt snapshot semantics; no dbt adapter invocation')
def export(j):
 lo=R.randint(1,1900);hi=R.randint(lo,min(2000,lo+50));s='select id,source_id,ntext,amount,body,event_date from etl_raw where id between %s and %s order by id';p=[lo,hi]
 policy='native_export' if j<1000 else ('csv_export' if j%2 else 'json_export');f={'native_export':'native_'+['csv','jsonline','parquet'][j%3]+'_unload','csv_export':'client_csv_roundtrip','json_export':'client_json_roundtrip'}[policy]
 add('export',f,s,p,diff=False,policy=policy,source=src('snowflake','copy-into-location'),meta={'run_id':j+1,'format':['csv','jsonline','parquet'][j%3] if policy=='native_export' else policy},strategy='Real INTO OUTFILE CSV / JSONLINE / PARQUET' if j<1000 else 'Application export of real query result and independent parser roundtrip')
fill('ingest',20000,ingest);fill('transform',30000,transform);fill('incremental',25000,incremental);fill('snapshot',15000,snapshot);fill('export',10000,export)
assert len(cases)==100000 and len(seen)==100000
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n')
(P/'fixtures.json').write_text(json.dumps({'raw':RAW},ensure_ascii=False));(P/'mapping.json').write_text(json.dumps(maps,ensure_ascii=False,indent=2));(P/'coverage.json').write_text(json.dumps({'total':len(cases),'unique':len(seen),'modules':counts,'families':collections.Counter(c['family'] for c in cases),'family_count':len(maps),'policies':collections.Counter(c['oracle_policy'] for c in cases)},ensure_ascii=False,indent=2))
