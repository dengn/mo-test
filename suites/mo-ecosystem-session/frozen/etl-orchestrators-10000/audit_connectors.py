import pathlib,json,sys,collections,time,datetime,hashlib
B=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(B));from codec import sha
import duckdb,pymysql
cases=json.loads((B/'fixtures.json').read_text());plans=json.loads((B/'case-plan.json').read_text())['cases'];out=[]
con=duckdb.connect(str(B/'fivetran-project/files/warehouse.db'),read_only=True);tables=con.execute('SHOW ALL TABLES').fetchall();print('FIVETRAN TABLES',tables,flush=True);(B/'fivetran-warehouse-schema.json').write_text(json.dumps(tables,default=str,indent=2))
table=next(r for r in tables if r[2]=='matrixone_cases');name='"'+table[1]+'"."'+table[2]+'"';rows=con.execute('SELECT endpoint,case_id,row_id,payload,_fivetran_deleted FROM '+name+' ORDER BY endpoint,case_id,row_id').fetchall();bycase=collections.defaultdict(list);keys=set();dupes=0;deleted=0
for port,cid,rid,payload,dead in rows:
 k=(port,cid,rid)
 if k in keys:dupes+=1
 keys.add(k)
 if dead:deleted+=1
 else:bycase[(int(port),int(cid))].append(json.loads(payload))
for spec in plans:
 if spec['component']!='fivetran':continue
 c=cases[spec['logical_case_id']-1];act=sorted(bycase[(spec['port'],spec['logical_case_id'])],key=lambda r:r[1]);exp=c['expected'];r=dict(spec,status='passed' if act==exp else 'fidelity_failed',expected_rows=len(exp),actual_rows=len(act),expected_sha256=c['expected_sha256'],actual_sha256=sha(act),scope='Official SDK2.12.1->official local Java tester->DuckDB; MO/MySQL typed SQL sources; explicit canonical STRING envelope preserves 20 source types; not native destination type mapping or SaaS certification')
 if act!=exp:r.update(expected_sample=exp[:3],actual_sample=act[:3])
 out.append(r)
con.close();(B/'results-fivetran.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out));(B/'fivetran-oracle-summary.json').write_text(json.dumps({'checked':len(out),'counts':dict(collections.Counter(r['status'] for r in out)),'duplicate_primary_keys':dupes,'soft_deleted_rows':deleted,'raw_rows':len(rows),'checkpoint_failure':'125 completed cases then uncheckpointed upsert; new process resumes next_case125 and reaches2000; final value oracle and duplicate keys checked; no non-idempotent effect exactly-once certification'},indent=2));print('FIVETRAN ORACLE',len(out),dict(collections.Counter(r['status'] for r in out)),flush=True)
A=B/'airbyte';receipts=[];results=[]
for engine,port,password in [('mo',6001,'111'),('mysql',13306,'types-local')]:
 ns='airbyte10k_'+engine;acks=[];errors=[]
 for line in (A/f'write-{engine}.jsonl').read_text().splitlines():
  try:x=json.loads(line)
  except ValueError:continue
  if x.get('type')=='STATE':acks.append(x)
  if x.get('type')=='TRACE' and x['trace']['type']=='ERROR':errors.append(x['trace']['error'])
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,database=ns,autocommit=True,charset='utf8mb4',read_timeout=90)
 with d.cursor() as cur:
  cur.execute('SHOW TABLES');ts=[r[0] for r in cur.fetchall()];print('AIRBYTE TABLES',engine,ts,flush=True);raw=next((t for t in ts if ('raw__stream_airbyte_events' in t or '_airbyte_raw_airbyte_events' in t)),None);data=[]
  if raw:cur.execute('SELECT _airbyte_data FROM `'+raw+'`');data=[json.loads(r[0]) for r in cur.fetchall()]
 d.close();latest={}
 for e in data:
  k=(int(e['case_id']),int(e['row_id']))
  if k not in latest or int(e['event_seq'])>int(latest[k]['event_seq']):latest[k]=e
 bycase=collections.defaultdict(list)
 for (cid,rid),e in latest.items():
  if not e.get('deleted'):bycase[cid].append(json.loads(e['payload']))
 receipts.append({'engine':engine,'port':port,'destination_ack_count':len(acks),'errors':errors,'raw_records':len(data),'raw_table':raw,'mapping':'Canonical STRING envelope outbox; test-side latest-event fold checks delivered events/deletes. Native destination raw append does NOT apply native target deletes. Failed native MO write cannot advance target checkpoint.'})
 for spec in plans:
  if spec['component']!='airbyte' or spec['port']!=port:continue
  c=cases[spec['logical_case_id']-1];act=sorted(bycase[spec['logical_case_id']],key=lambda r:r[1]);exp=c['expected'];r=dict(spec,status='execution_blocked' if errors or not acks else ('passed' if act==exp else 'fidelity_failed'),expected_rows=len(exp),actual_rows=len(act),expected_sha256=c['expected_sha256'],actual_sha256=sha(act),execution_evidence=f'airbyte/write-{engine}.jsonl',scope='Official source snapshot -> official raw MySQL destination, explicit lossless outbox STRING profile; scenario assertions within one connector execution per target, not1000 isolated sync attempts')
  if errors:r['root_cause']=errors[0].get('message','')[:300];r['related_issue']=29849
  if act!=exp and not errors:r.update(expected_sample=exp[:3],actual_sample=act[:3])
  results.append(r)
(B/'airbyte-oracle-summary.json').write_text(json.dumps({'checked':len(results),'counts':dict(collections.Counter(r['status'] for r in results)),'receipts':receipts},ensure_ascii=False,indent=2));(B/'results-airbyte-native.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results));print('AIRBYTE ORACLE',len(results),dict(collections.Counter(r['status'] for r in results)),flush=True)
