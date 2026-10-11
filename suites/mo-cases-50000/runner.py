import json,time,datetime,decimal,math,hashlib,collections,threading,concurrent.futures,argparse,sys,os
from pathlib import Path
import pymysql
P=Path(__file__).resolve().parent
DB=os.environ.get('MO_SUITE_DATABASE') or ((P/'database.txt').read_text().strip() if (P/'database.txt').exists() else 'suite50_'+str(int(time.time())))
if not os.environ.get('MO_SUITE_DATABASE'):(P/'database.txt').write_text(DB+'\n')
local=threading.local();lock=threading.Lock()
def connect(engine,db=DB,timeout=20):
 c=pymysql.connect(host='127.0.0.1',port=6001 if engine=='mo' else 63306,user='root',password='111' if engine=='mo' else '',database=db,autocommit=True,read_timeout=timeout,write_timeout=timeout,connect_timeout=5,charset='utf8mb4',ssl_disabled=True)
 if engine=='mo':
  for s in ['set experimental_hnsw_index=1','set experimental_fulltext2_index=1','set hnsw_threads_search=1','set probe_limit=128']:
   query(c,s)
 return c
def query(c,s,p=None):
 with c.cursor() as q:
  q.execute(s,p) if p else q.execute(s)
  return q.fetchall() if q.description else []
def bootstrap():
 f=json.loads((P/'fixtures.json').read_text());v={}
 for engine in ['mysql','mo']:
  c=connect(engine,None,180);query(c,f'create database if not exists {DB}');query(c,f'use {DB}')
  v[engine]={'version':query(c,'select version()'),'sql_mode':query(c,'select @@sql_mode')}
  query(c,'create table seed(id bigint primary key,grp int,val bigint,nullable int,name varchar(100))')
  with c.cursor() as q:q.executemany('insert into seed values(%s,%s,%s,%s,%s)',f['seed'])
  if engine=='mo':
   query(c,'set hnsw_threads_build=4')
   for t in ['vectors','vh','vi']:
    query(c,f'create table {t}(id bigint primary key,v vecf32(3))')
    with c.cursor() as q:q.executemany(f'insert into {t} values(%s,%s)',f['vectors'])
   query(c,"create index ann using hnsw on vh(v) m=32 ef_construction=200 ef_search=1000 op_type 'vector_l2_ops'")
   query(c,'alter table vh alter reindex ann hnsw force_sync')
   query(c,"create index ann using ivfflat on vi(v) lists=16 op_type 'vector_l2_ops'")
   for t,kind in [('ft','fulltext'),('ft2','fulltext2')]:
    query(c,f'create table {t}(id bigint primary key,body text)')
    with c.cursor() as q:q.executemany(f'insert into {t} values(%s,%s)',[(int(i),b) for i,b in f['docs'].items()])
    query(c,f'create {kind} index txt on {t}(body)')
   zh=[(1,'苹果 香蕉'),(2,'香蕉 苹果'),(3,'苹果'),(4,'香蕉'),(5,'大学怎么网上选宿舍'),(6,'大学网上宿舍')]
   for parser in ['ngram','gojieba']:
    query(c,f'create table fc_{parser}(id bigint primary key,body text)')
    with c.cursor() as q:q.executemany(f'insert into fc_{parser} values(%s,%s)',zh)
    query(c,f'create fulltext index txt on fc_{parser}(body) with parser {parser}')
  c.close()
 (P/'versions.json').write_text(json.dumps(v,default=str,indent=2));print('bootstrap ready',DB,flush=True)
def norm(x):
 if isinstance(x,datetime.timedelta):
  total=x.days*86400000000+x.seconds*1000000+x.microseconds;sign='-' if total<0 else '';total=abs(total);hours,rem=divmod(total,3600000000);minutes,rem=divmod(rem,60000000);seconds,micros=divmod(rem,1000000);return f'{sign}{hours:02d}:{minutes:02d}:{seconds:02d}'+(f'.{micros:06d}' if micros else '')
 if isinstance(x,bytes):return x.decode('utf8',errors='replace')
 if isinstance(x,(datetime.datetime,datetime.date,datetime.time)):return str(x)
 if isinstance(x,decimal.Decimal):return str(x)
 if isinstance(x,(tuple,list)):return [norm(a) for a in x]
 if isinstance(x,dict):return {k:norm(v) for k,v in x.items()}
 return x
def equal(a,b,tol,mode='ordered'):
 if mode=='json' and isinstance(a,str):
  try:a=json.loads(a)
  except:pass
 if mode=='json' and isinstance(b,str):
  try:b=json.loads(b)
  except:pass
 if a is None or b is None:return a is b
 if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):return len(a)==len(b) and all(equal(x,y,tol,mode) for x,y in zip(a,b))
 if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equal(a[k],b[k],tol,mode) for k in a)
 if isinstance(a,(int,float,decimal.Decimal)) and isinstance(b,(int,float,decimal.Decimal)):
  if isinstance(a,float) or isinstance(b,float):return math.isclose(float(a),float(b),rel_tol=tol,abs_tol=tol)
  return a==b
 if isinstance(a,decimal.Decimal) and isinstance(b,str):
  try:return a==decimal.Decimal(b)
  except:pass
 if isinstance(b,decimal.Decimal) and isinstance(a,str):
  try:return b==decimal.Decimal(a)
  except:pass
 return norm(a)==norm(b)
def ann(a,w,tol):
 if len(a)!=w['k'] or len({int(r[0]) for r in a})!=len(a):return False
 for i,d in a:
  if not 1<=int(i)<=200:return False
  v=[((int(i)*17+j*11)%101-50)/10 for j in range(3)]
  exact=math.sqrt(sum((x-y)**2 for x,y in zip(v,w['query'])))
  if not math.isclose(float(d),exact,rel_tol=tol,abs_tol=tol) or exact>w['cutoff']+tol:return False
 return True
def execute(engine,case):
 cs=getattr(local,'connections',None)
 if cs is None:cs={};local.connections=cs
 if engine not in cs:cs[engine]=connect(engine)
 c=cs[engine];table='case_'+case['id'].lower();ddl=case['module']=='ddl_transactions';out=None;error=None
 try:
  for st in case['statements']:out=query(c,st['sql'].replace('{table}',table),st.get('params'))
 except Exception as e:
  error={'code':e.args[0] if e.args else None,'message':str(e),'type':type(e).__name__}
 finally:
  if ddl:
   try:query(c,'rollback');query(c,f'drop table if exists {table}')
   except Exception as e:error=error or {'code':'cleanup','message':str(e),'type':type(e).__name__}
  if error and error['type'] in ['OperationalError','InterfaceError'] and error['code'] in [2006,2013,0]:
   try:c.close()
   except:pass
   cs.pop(engine,None)
 return out,error
def runone(case):
 t=time.monotonic();a,ae=execute('mo',case);first_error=ae;retries=0
 while ae and ae['code'] in [20706,20619,20618] and retries<3:
  time.sleep(0.01*(retries+1));a,ae=execute('mo',case);retries+=1
 b,be=(None,None)
 if case['mysql_differential']:b,be=execute('mysql',case)
 w=case['expected'];tol=case['tolerance'];mode=case['compare_mode']
 if case['expect_error']:status='pass_expected_error' if ae else 'candidate_missing_error'
 elif ae:
  if be:status='both_rejected' if case['mysql_differential'] else 'execution_error'
  else:status='mo_execution_error'
 elif be:status='reference_rejected'
 elif mode=='ann':status='pass' if ann(a,w,tol) else 'ann_boundary_or_result'
 elif case['mysql_differential']:
  ab=equal(a,b,tol,mode);aw=w is None or equal(a,w,tol,mode);bw=w is None or equal(b,w,tol,mode)
  if ab and aw:status='pass'
  elif ab:status='oracle_issue'
  elif aw and not bw:status='reference_difference'
  elif bw:status='candidate_wrong_result'
  else:status='three_way_difference'
 else:status='pass' if equal(a,w,tol,mode) else 'candidate_wrong_result'
 result={'id':case['id'],'module':case['module'],'family':case['family'],'status':status,'seconds':round(time.monotonic()-t,6),'mo_error':ae,'mysql_error':be,'retries':retries,'initial_error':first_error if retries else None,'mo_rows':len(a) if a is not None else None,'mysql_rows':len(b) if b is not None else None,'mo_result_sha256':hashlib.sha256(json.dumps(norm(a),ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
 if not status.startswith('pass'):result.update(actual=norm(a),reference=norm(b),expected=w)
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bootstrap',action='store_true');ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--workers',type=int,default=8);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--ids');args=ap.parse_args()
 if args.bootstrap:bootstrap();return
 cases=[json.loads(l) for l in (P/'cases.jsonl').open()]
 if args.ids:
  ids=set(Path(args.ids).read_text().split());cases=[c for c in cases if c['id'] in ids]
 if args.calibrate:
  cnt=collections.Counter();selected=[]
  for c in cases:
   if cnt[c['family']]<args.calibrate:selected.append(c);cnt[c['family']]+=1
  cases=selected
 out=P/args.output;done=set()
 if out.exists():done={json.loads(l)['id'] for l in out.open()}
 cases=[c for c in cases if c['id'] not in done];counts=collections.Counter();start=time.time();last=start
 with out.open('a') as f:
  for module in dict.fromkeys(c['module'] for c in cases):
   batch=[c for c in cases if c['module']==module];workers=min(args.workers,4) if module=='ddl_transactions' else args.workers
   print('module',module,'cases',len(batch),'workers',workers,flush=True)
   with concurrent.futures.ThreadPoolExecutor(workers) as ex:
    futures=[ex.submit(runone,c) for c in batch]
    for fu in concurrent.futures.as_completed(futures):
     r=fu.result();f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');counts[r['status']]+=1
     if sum(counts.values())%500==0 or time.time()-last>=15:
      f.flush();print(json.dumps({'completed':sum(counts.values()),'counts':counts,'elapsed':round(time.time()-start,2)},ensure_ascii=False),flush=True);last=time.time()
   f.flush();print('module done',module,dict(counts),flush=True)
 print('DONE',len(done)+sum(counts.values()),dict(counts),'seconds',time.time()-start,flush=True)
if __name__=='__main__':main()
