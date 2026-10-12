import json,pathlib,sys,datetime,decimal,hashlib,time,traceback,argparse
B=pathlib.Path(__file__).resolve().parent;decimal.getcontext().prec=80
P=argparse.ArgumentParser();P.add_argument('--component',required=True);P.add_argument('--port',type=int,required=True);P.add_argument('--inject-retry',action='store_true');a=P.parse_args()
def decode(v):
 if not isinstance(v,dict) or 'kind' not in v:return v
 k=v['kind'];x=v['value']
 return {'decimal':lambda:decimal.Decimal(x),'datetime':lambda:datetime.datetime.fromisoformat(x),'date':lambda:datetime.date.fromisoformat(x),'duration':lambda:datetime.timedelta(microseconds=x),'bytes':lambda:bytes.fromhex(x)}[k]()
def normalize(v,n):
 if v is None:return ['sql_null']
 if n.startswith('json'):return ['json',json.loads(v) if isinstance(v,(str,bytes)) else v]
 if n.startswith('decimal'):return str(decimal.Decimal(v).normalize())
 if n in ['varbinary','blob']:return bytes(v).hex()
 if n=='date':return v.isoformat()
 if n=='datetime6':return v.isoformat(timespec='microseconds')
 if n=='time6':return (v.days*86400+v.seconds)*1000000+v.microseconds
 if n=='float32':return format(float(v),'.6g')
 if n=='double':return float(v).hex() if float(v)!=0 else '0'
 if n=='char_padding':return str(v).rstrip(' ')
 if n=='boolean':return bool(v)
 if n in ['tinyint','smallint','int32','int64','uint64']:return int(v)
 return str(v)
def canon(rows,n):return [[int(r[0]),int(r[1]),normalize(r[2],n),str(r[3]),int(r[4])] for r in sorted(rows,key=lambda r:(r[0],r[1]))]
def sha(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def connect():
 if a.component=='airflow':
  from airflow.providers.mysql.hooks.mysql import MySqlHook
  from airflow.sdk import Connection
  c=Connection(conn_id='matrixone_test',conn_type='mysql',host='127.0.0.1',port=a.port,login='root',password='111' if a.port==6001 else 'types-local',schema='orchestrator10000',extra=json.dumps({'client':'mysql-connector-python','ssl_disabled':True}))
  return MySqlHook(mysql_conn_id=c.conn_id,connection=c).get_conn()
 import pymysql
 return pymysql.connect(host='127.0.0.1',port=a.port,user='root',password='111' if a.port==6001 else 'types-local',database='orchestrator10000',charset='utf8mb4',autocommit=False,read_timeout=90)
path=B/f'results-{a.component}-{a.port}.jsonl';finished={json.loads(l)['id'] for l in path.read_text().splitlines()} if path.exists() else set()
cs=json.loads((B/'fixtures.json').read_text());d=connect();cur=d.cursor();n=0;bad=0
for c in cs:
 cid=c['logical_case_id'];p=c['profile'];token=f'{a.component}_{p}_{c["scenario"]}_{c["seed"]}_{a.port}'
 if token in finished:continue
 t=a.component+'_'+p;rows=[[decode(v) for v in r] for r in c['rows']];changes=[[decode(v) for v in r] for r in c['changes']];start=time.monotonic();out={'id':token,'component':a.component,'port':a.port,'logical_case_id':cid,'profile':p,'scenario':c['scenario'],'seed':c['seed'],'driver':'Airflow MySqlHook/mysql-connector-python' if a.component=='airflow' else 'DolphinScheduler Shell task/explicit PyMySQL adapter'}
 try:
  cur.execute('DELETE FROM '+t+' WHERE case_id=%s',(cid,));cur.executemany('INSERT INTO '+t+' VALUES(%s,%s,%s,%s,%s)',rows)
  if c['scenario']=='chunked_append':
   cur.execute('DELETE FROM '+t+' WHERE case_id=%s',(cid,))
   for i in range(0,len(rows),3):cur.executemany('INSERT INTO '+t+' VALUES(%s,%s,%s,%s,%s)',rows[i:i+3]);d.commit()
  if c['scenario']=='native_transform':
   cur.execute('DELETE FROM '+t+' WHERE case_id=%s AND MOD(id,2)<>%s',(cid,c['seed']%2));cur.execute('UPDATE '+t+' SET label=CONCAT(label,%s),rev=rev+%s WHERE case_id=%s',('→ETL'+str(c['seed']),c['seed']+1,cid))
  if c['scenario']=='staging_merge':
   for r in changes:
    cur.execute('SELECT COUNT(*) FROM '+t+' WHERE case_id=%s AND id=%s',(cid,r[1]));present=cur.fetchone()[0]
    if present:cur.execute('UPDATE '+t+' SET v=%s,label=%s,rev=%s WHERE case_id=%s AND id=%s',(r[2],r[3],r[4],cid,r[1]))
    else:cur.execute('INSERT INTO '+t+' VALUES(%s,%s,%s,%s,%s)',r)
  if c['scenario']=='tombstone_delete':
   for i in c['dead']:cur.execute('DELETE FROM '+t+' WHERE case_id=%s AND id=%s',(cid,i))
  d.commit();cur.execute('SELECT case_id,id,v,label,rev FROM '+t+' WHERE case_id=%s ORDER BY id',(cid,));actual=canon(cur.fetchall(),p);expected=c['expected'];out.update(status='passed' if actual==expected else 'fidelity_failed',expected_rows=len(expected),actual_rows=len(actual),expected_sha256=c['expected_sha256'],actual_sha256=sha(actual))
  if actual!=expected:out.update(expected_sample=expected[:3],actual_sample=actual[:3]);bad+=1
 except Exception as e:
  d.rollback();out.update(status='execution_failed',error=repr(e),traceback=traceback.format_exc());bad+=1
 out['elapsed_s']=time.monotonic()-start
 with path.open('a') as f:f.write(json.dumps(out,ensure_ascii=False,default=str)+'\n')
 n+=1
 if n%50==0:print('PROGRESS',a.component,a.port,n,'failures',bad,flush=True)
 flag=B/f'{a.component}-{a.port}-retry-injected'
 if a.inject_retry and n==50 and not flag.exists():
  flag.write_text(json.dumps({'deliberate_exit_after_completed_cases':50,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'purpose':'real orchestrator task retry, durable receipts resumed; not database failure'}));raise RuntimeError('Deliberate task failure: verify native orchestrator retry and receipt resume')
cur.close();d.close();print('COMPLETED',a.component,a.port,'new',n,'failed',bad,flush=True)
if bad:raise RuntimeError(f'{bad} case failures; details persisted')
