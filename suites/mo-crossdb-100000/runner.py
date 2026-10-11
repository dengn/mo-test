import sys,json,time,collections,concurrent.futures,argparse
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,'/workspace/mo-cases-50000');import runner as base

def bootstrap():
 f=json.loads((P/'fixtures.json').read_text())
 for eng in ['mo','mysql']:
  c=base.connect(eng,timeout=180)
  for s in ['create table cross_events(id bigint primary key,device int,epoch bigint,val bigint,nullable bigint,state int,category int)','create table cross_devices(id int primary key,region int,name varchar(100))','create table cross_entities(id bigint primary key,n bigint,name varchar(100),j json)','create table cross_tags(item_id bigint,pos int,tag int)']:
   base.query(c,s)
  with c.cursor() as q:
   q.executemany('insert into cross_events values(%s,%s,%s,%s,%s,%s,%s)',f['events']);q.executemany('insert into cross_devices values(%s,%s,%s)',f['devices']);q.executemany('insert into cross_tags values(%s,%s,%s)',f['tags'])
  if eng=='mo':
   base.query(c,'create table cross_items(id bigint primary key,grp int,payload json,v vecf32(3),w vecf32(3),body text)')
   with c.cursor() as q:q.executemany('insert into cross_items values(%s,%s,%s,%s,%s,%s)',f['items'])
   base.query(c,'create fulltext index txt on cross_items(body)')
  else:
   base.query(c,'create table cross_items(id bigint primary key,grp int,payload json,v text,w text,body text)')
   with c.cursor() as q:q.executemany('insert into cross_items values(%s,%s,%s,%s,%s,%s)',f['items'])
  c.close()
 print('fixtures ready',base.DB,flush=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bootstrap',action='store_true');ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--workers',type=int,default=24);ap.add_argument('--ids');a=ap.parse_args()
 if a.bootstrap:bootstrap();return
 cases=list(map(json.loads,(P/'cases.jsonl').open()))
 if a.ids:
  ids=set(Path(a.ids).read_text().split());cases=[c for c in cases if c['id'] in ids]
 if a.calibrate:
  counts=collections.Counter();out=[]
  for c in cases:
   if not c.get('meta') and counts[c['family']]<a.calibrate:out.append(c);counts[c['family']]+=1
  cases=out
 dest=P/a.output;done={json.loads(l)['id'] for l in dest.open()} if dest.exists() else set();cases=[c for c in cases if c['id'] not in done];cc=collections.Counter();t=time.time();last=t
 with dest.open('a') as f:
  for engine in dict.fromkeys(c['module'] for c in cases):
   batch=[c for c in cases if c['module']==engine];print('engine',engine,'cases',len(batch),flush=True)
   with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
    for r in ex.map(base.runone,batch):
     f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');cc[r['status']]+=1
     if sum(cc.values())%1000==0 or time.time()-last>15:
      f.flush();last=time.time();print(json.dumps({'completed':sum(cc.values()),'counts':cc,'elapsed':round(time.time()-t,2)}),flush=True)
   f.flush();print('engine done',engine,dict(cc),flush=True)
 print('DONE',len(done)+sum(cc.values()),dict(cc),time.time()-t,flush=True)
if __name__=='__main__':main()
