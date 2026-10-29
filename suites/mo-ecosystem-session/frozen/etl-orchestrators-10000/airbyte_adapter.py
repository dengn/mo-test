import json,pathlib,sys,pymysql,datetime,decimal,collections,traceback
B=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(B));from codec import canon,sha
cs=json.loads((B/'fixtures.json').read_text());decimal.getcontext().prec=80;events=[]
for line in (B/'airbyte/read.jsonl').read_text().splitlines():
 try:x=json.loads(line)
 except ValueError:continue
 if x.get('type')=='RECORD':events.append(x['record']['data'])
events.sort(key=lambda e:int(e['event_seq']))
def value(v,p):
 if v==['sql_null']:return None
 if p.startswith('json'):return json.dumps(v[1],ensure_ascii=False,separators=(',',':'))
 if p.startswith('decimal'):return decimal.Decimal(v)
 if p in ['varbinary','blob']:return bytes.fromhex(v)
 if p=='date':return datetime.date.fromisoformat(v)
 if p=='datetime6':return datetime.datetime.fromisoformat(v)
 if p=='time6':return datetime.timedelta(microseconds=v)
 if p=='double':return float.fromhex(v)
 if p=='float32':return float(v)
 return v

def db():return pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='orchestrator10000',autocommit=False,charset='utf8mb4',read_timeout=90)
with db() as d,d.cursor() as cur:
 cur.execute('CREATE TABLE IF NOT EXISTS airbyte_adapter_checkpoint(stream_name VARCHAR(64) PRIMARY KEY,event_seq BIGINT)');cur.execute("SELECT event_seq FROM airbyte_adapter_checkpoint WHERE stream_name='airbyte_events'")
 if cur.fetchone() is None:
  cur.execute("INSERT INTO airbyte_adapter_checkpoint VALUES('airbyte_events',0)")
  for p in {c['profile']:c for c in cs}.values():cur.execute('CREATE TABLE IF NOT EXISTS airbyte_adapter_'+p['profile']+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(256),rev BIGINT,PRIMARY KEY(case_id,id))')
 d.commit()
receipts=[]
for phase in ['injected_commit_then_disconnect','resume','replay']:
 processed=0
 try:
  with db() as d,d.cursor() as cur:
   cur.execute("SELECT event_seq FROM airbyte_adapter_checkpoint WHERE stream_name='airbyte_events'");initial=int(cur.fetchone()[0]);pending=[e for e in events if int(e['event_seq'])>initial]
   for start in range(0,len(pending),100):
    batch=pending[start:start+100]
    for e in batch:
     cid=int(e['case_id']);rid=int(e['row_id']);p=e['profile'];t='airbyte_adapter_'+p
     if e.get('deleted'):cur.execute('DELETE FROM '+t+' WHERE case_id=%s AND id=%s',(cid,rid))
     else:
      r=json.loads(e['payload']);v=value(r[2],p);cur.execute('SELECT COUNT(*) FROM '+t+' WHERE case_id=%s AND id=%s',(cid,rid));exists=cur.fetchone()[0]
      if exists:cur.execute('UPDATE '+t+' SET v=%s,label=%s,rev=%s WHERE case_id=%s AND id=%s',(v,r[3],r[4],cid,rid))
      else:cur.execute('INSERT INTO '+t+' VALUES(%s,%s,%s,%s,%s)',(cid,rid,v,r[3],r[4]))
    cur.execute("UPDATE airbyte_adapter_checkpoint SET event_seq=%s WHERE stream_name='airbyte_events'",(int(batch[-1]['event_seq']),));d.commit();processed+=len(batch)
    if phase=='injected_commit_then_disconnect' and processed>=300 and not (B/'airbyte-adapter-injected').exists():(B/'airbyte-adapter-injected').write_text(str(batch[-1]['event_seq']));raise RuntimeError('Deliberate loss of application acknowledgement after committed native MO batch/checkpoint')
   receipts.append({'phase':phase,'initial_checkpoint':initial,'processed_events':processed,'status':'completed'})
 except Exception as e:receipts.append({'phase':phase,'status':'injected_failure' if 'Deliberate' in str(e) else 'unexpected_failure','error':str(e),'processed_events':processed})
(B/'airbyte-adapter-recovery.json').write_text(json.dumps({'scope':'Explicit Python SQL sink consumes real official Airbyte source records; SQL effects/checkpoint atomic within same MO transaction. This is not the official Airbyte destination and does not replace its blocked STATE ACK. Event sequence and canonical STRING envelope are adapter contracts.','phases':receipts},indent=2))
results=[]
with db() as d,d.cursor() as cur:
 for p in {c['profile']:c for c in cs}.values():
  n=p['profile'];cur.execute('SELECT case_id,id,v,label,rev FROM airbyte_adapter_'+n+' ORDER BY case_id,id');rows=cur.fetchall();bycase=collections.defaultdict(list)
  for r in rows:bycase[r[0]].append(r)
  for c in cs:
   if c['profile']!=n:continue
   actual=canon(bycase[c['logical_case_id']],n);expected=c['expected'];out={'id':f'airbyte_{n}_{c["scenario"]}_{c["seed"]}_6001','component':'airbyte','port':6001,'logical_case_id':c['logical_case_id'],'profile':n,'scenario':c['scenario'],'seed':c['seed'],'status':'passed' if actual==expected else 'fidelity_failed','native_destination_status':'execution_blocked','related_issue':29849,'configured_path':'official_source_to_explicit_sql_sink','expected_rows':len(expected),'actual_rows':len(actual),'expected_sha256':c['expected_sha256'],'actual_sha256':sha(actual)}
   if actual!=expected:out.update(expected_sample=expected[:3],actual_sample=actual[:3])
   results.append(out)
(B/'results-airbyte-adapted.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results));print('ADAPTED ORACLE',len(results),dict(collections.Counter(r['status'] for r in results)),receipts,flush=True)
