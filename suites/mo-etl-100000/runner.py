import sys,json,csv,time,hashlib,collections,concurrent.futures,argparse,decimal,io
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,'/workspace/mo-cases-50000');import runner as base

def bootstrap():
 f=json.load(open(P/'fixtures.json'))
 for eng in ['mo','mysql']:
  c=base.connect(eng,timeout=180)
  for s in ['create table etl_raw(id bigint primary key,source_id int,_fivetran_synced bigint,_fivetran_deleted boolean,ntext varchar(100),amount decimal(20,4),body text,meta json,event_date varchar(30))','create table etl_ingest(id bigint primary key,ntext varchar(100),body text,meta json)','create table etl_csv(batch bigint,rid bigint,n bigint,body text,meta json,primary key(batch,rid))','create table etl_target(id bigint primary key,n bigint,seq bigint,deleted boolean,synced bigint,body text)','create table etl_history(key_id bigint,valid_from bigint,valid_to bigint,n bigint,deleted boolean,primary key(key_id,valid_from))']:
   base.query(c,s)
  with c.cursor() as q:q.executemany('insert into etl_raw values(%s,%s,%s,%s,%s,%s,%s,%s,%s)',f['raw'])
  c.close()
 print('fixtures ready',base.DB,flush=True)
def conn():
 cs=getattr(base.local,'connections',None)
 if cs is None:cs={};base.local.connections=cs
 if 'mo' not in cs:cs['mo']=base.connect('mo',timeout=60)
 return cs['mo']
def runone(case):
 policy=case['oracle_policy']
 if policy=='normal':return base.runone(case)
 t=time.monotonic();c=conn();expected=None;actual=None;error=None;path=None
 try:
  if policy=='native_csv':
   batch=case['meta']['batch'];rows=case['meta']['rows'];directory=P/'inputs';directory.mkdir(exist_ok=True);path=directory/(case['id']+'.csv')
   with path.open('w',newline='') as f:
    q=csv.writer(f);q.writerow(['batch','rid','n','body','meta']);q.writerows(rows)
   st=case['statements'][0];s=st['sql'].replace('{input}',"'"+str(path)+"'");base.query(c,s)
   actual=base.query(c,'select batch,rid,n,body,meta from etl_csv where batch=%s order by rid',[batch]);expected=rows
   status='pass' if base.equal(actual,expected,1e-6,'json') else 'candidate_wrong_result'
  else:
   st=case['statements'][0];expected=base.query(c,st['sql'],st['params']);expected=base.norm(expected);directory=P/'exports';directory.mkdir(exist_ok=True)
   if policy=='native_export':
    fmt=case['meta']['format'];ext={'csv':'csv','jsonline':'jsonl','parquet':'parquet'}[fmt];path=directory/(case['id']+'.'+ext)
    if path.exists():path.unlink()
    opts=" fields terminated by ',' enclosed by '\"' lines terminated by '\\n' header 'true'" if fmt=='csv' else ''
    with c.cursor() as q:q.execute(st['sql']+f" into outfile '{path}' format '{fmt}'"+opts,st['params'])
    if fmt=='csv':
     with path.open(newline='') as f:reader=csv.reader(f);header=next(reader);actual=list(reader)
     expected=[[str(x) if x is not None else '\\N' for x in row] for row in expected]
    elif fmt=='jsonline':
     names=['id','source_id','ntext','amount','body','event_date'];rr=[json.loads(l) for l in path.read_text().splitlines() if l];actual=[[r[n] for n in names] for r in rr]
     # JSON permits either numeric or string DECIMAL encoding, preserving exact numeric value.
     for rows in [actual,expected]:
      for row in rows:row[3]=str(decimal.Decimal(str(row[3])))
    else:
     import pyarrow.parquet as pq
     names=['id','source_id','ntext','amount','body','event_date'];table=pq.read_table(path);actual=[[r[n] for n in names] for r in table.to_pylist()];actual=base.norm(actual)
     for row in actual:row[3]=str(decimal.Decimal(str(row[3])))
     for row in expected:row[3]=str(decimal.Decimal(str(row[3])))
   elif policy=='csv_export':
    path=directory/(case['id']+'.csv')
    with path.open('w',newline='') as f:csv.writer(f).writerows(expected)
    with path.open(newline='') as f:actual=list(csv.reader(f))
    expected=[[str(v) if v is not None else '' for v in row] for row in expected]
   else:
    path=directory/(case['id']+'.jsonl');path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in expected));actual=[json.loads(l) for l in path.read_text().splitlines()]
   status='pass' if base.equal(actual,expected,1e-6) else 'candidate_export_corruption'
 except Exception as e:status='etl_execution_error';error={'type':type(e).__name__,'message':str(e),'code':e.args[0] if e.args else None}
 result=dict(id=case['id'],module=case['module'],family=case['family'],status=status,seconds=time.monotonic()-t,mo_error=error,artifact=str(path) if path else None,file_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None)
 if status!='pass':result.update(actual=base.norm(actual),expected=expected)
 return result
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bootstrap',action='store_true');ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--workers',type=int,default=24);ap.add_argument('--ids');a=ap.parse_args()
 if a.bootstrap:bootstrap();return
 cases=list(map(json.loads,(P/'cases.jsonl').open()))
 if a.ids:
  ids=set(Path(a.ids).read_text().split());cases=[c for c in cases if c['id'] in ids]
 if a.calibrate:
  z=[];cc=collections.Counter()
  for c in cases:
   if c['module'] in ['transform','export'] and cc[c['family']]<a.calibrate:z.append(c);cc[c['family']]+=1
  cases=z
 dest=P/a.output;done={json.loads(l)['id'] for l in dest.open()} if dest.exists() else set();cases=[c for c in cases if c['id'] not in done];cc=collections.Counter();t=time.time();last=t
 with dest.open('a') as f:
  for module in dict.fromkeys(c['module'] for c in cases):
   batch=[c for c in cases if c['module']==module];print('module',module,len(batch),flush=True)
   with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
    for r in ex.map(runone,batch):
     f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');cc[r['status']]+=1
     if sum(cc.values())%1000==0 or time.time()-last>15:
      f.flush();last=time.time();print(json.dumps({'completed':sum(cc.values()),'counts':cc,'elapsed':round(time.time()-t,2)}),flush=True)
   f.flush();print('module done',module,dict(cc),flush=True)
 print('DONE',len(done)+sum(cc.values()),dict(cc),time.time()-t,flush=True)
if __name__=='__main__':main()
