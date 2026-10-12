"""Original synthetic event-time fixtures, separate from every previous suite."""
import hashlib,json,os,re
from pathlib import Path
import duckdb,numpy as np,pandas as pd,pymysql
from sqlalchemy import URL,create_engine

ROOT=Path(__file__).resolve().parent
DB=os.getenv('MO_TS_DATABASE','ds_timeseries_20261011')
SEED=2026101117
SCHEMAS={
 'entities':'eid INT PRIMARY KEY,region INT,sector INT,scale DOUBLE',
 'calendar':'day INT PRIMARY KEY,week INT,weekday INT,utc_min BIGINT,offset_min INT',
 'measurements':'rid INT PRIMARY KEY,event_id INT,eid INT,day INT,minute BIGINT,revision INT,received_day INT,value DOUBLE,valid INT',
 'trades':'tid INT PRIMARY KEY,eid INT,day INT,amount DOUBLE,settled INT',
 'reversals':'rid INT PRIMARY KEY,tid INT,day INT,amount DOUBLE',
 'orders':'oid INT PRIMARY KEY,eid INT,day INT,qty INT',
 'shipments':'sid INT PRIMARY KEY,oid INT,day INT,qty INT',
 'inventory':'eid INT,day INT,on_hand INT',
 'capacity':'region INT,day INT,available DOUBLE',
 'weather':'region INT,day INT,temp DOUBLE',
 'prices':'sector INT,day INT,price DOUBLE',
 'fx':'region INT,day INT,rate DOUBLE',
 'targets':'sector INT,weekday INT,target DOUBLE',
 'outages':'qid INT PRIMARY KEY,eid INT,start_day INT,end_day INT,severity DOUBLE',
 'policies':'eid INT,valid_from INT,valid_to INT,budget DOUBLE',
 'interventions':'eid INT,day INT,effect DOUBLE',
 'events':'event_id INT PRIMARY KEY,eid INT,day INT,minute BIGINT,received_min BIGINT,kind INT,magnitude DOUBLE',
 'edges':'src INT,dst INT,weight DOUBLE',
}

def tables():
 rng=np.random.default_rng(SEED);eid=np.arange(1,129,dtype=np.int64);day=np.arange(160,dtype=np.int64)
 ent=pd.DataFrame(dict(eid=eid,region=eid%4,sector=eid%5,scale=20.+eid%17))
 cal=pd.DataFrame(dict(day=day,week=day//7,weekday=day%7,utc_min=28401120+day*1440,offset_min=np.where(day<60,60,120)))
 measurements=[];trades=[];orders=[];events=[];outages=[];interventions=[]
 for e in eid:
  for d in range(12,148):
   if e<125 and (e*7+d)%9!=0:
    for tick in range(1+(e+d)%3):
     event=int(e*10000+d*10+tick);minute=int(28401120+d*1440+(e*13+d*17)%120)
     value=round(20+e%9+np.sin(d/7+e)*4+.035*d+rng.normal(0,.8),8)
     for revision in [0,1]:
      val=value+(round(np.sin(e+d)*.7,8) if revision else 0)
      if (e+d+tick)%23==0:val=np.nan
      measurements.append((len(measurements)+1,event,e,d,minute,revision,d+(0 if revision==0 else 1+(e+d)%4),val,int(not(revision and (e+d+tick)%29==0))))
   if e<125 and (e+d)%5!=0:
    for tick in range(2):trades.append((len(trades)+1,e,d,round(15+(e*3+d*7+tick)%85+rng.normal(0,2),8),int((e+d+tick)%11!=0)))
   if e<125 and (e+d)%7!=0:orders.append((len(orders)+1,e,d,int(1+(e*5+d*3)%12)))
   if e<125 and (e*11+d)%4!=0:
    # Duplicate event-time peers, tied magnitudes, irregular gaps, and late arrival.
    for tick in range(1+(e+d)%3):
     minute=int(28401120+d*1440+(e*13+d*17)%180+(0 if tick<2 else 13))
     events.append((len(events)+1,e,d,minute,minute+int((e+d+tick)%5)*720,int((e+d+tick)%5),float((e*7+d+tick)%21-5)))
   if (e+d)%31==0:interventions.append((e,d,round(.2+(e%7)*.13,8)))
  for k in range(3):
   start=int(19+(e*11+k*37)%100);outages.append((len(outages)+1,e,start,start+1+(e+k)%7,float(.3+(e+k)%5*.14)))
 m=pd.DataFrame(measurements,columns=['rid','event_id','eid','day','minute','revision','received_day','value','valid']);t=pd.DataFrame(trades,columns=['tid','eid','day','amount','settled']);o=pd.DataFrame(orders,columns=['oid','eid','day','qty']);ev=pd.DataFrame(events,columns=['event_id','eid','day','minute','received_min','kind','magnitude'])
 chosen=t[t.tid%19==0];rev=pd.DataFrame(dict(rid=np.arange(1,len(chosen)+1),tid=chosen.tid.to_numpy(),day=chosen.day.to_numpy()+2,amount=chosen.amount.to_numpy()*.3))
 shipments=[]
 for row in o.itertuples(index=False):
  for part in range(1+(row.oid%4==0)):
   shipments.append((len(shipments)+1,row.oid,row.day+int(row.oid%9),int(row.qty//2 if row.oid%4==0 and part==0 else row.qty-row.qty//2 if row.oid%4==0 else row.qty)))
 g=pd.MultiIndex.from_product([eid,day],names=['eid','day']).to_frame(index=False);rg=pd.MultiIndex.from_product([range(4),day],names=['region','day']).to_frame(index=False);sg=pd.MultiIndex.from_product([range(5),day],names=['sector','day']).to_frame(index=False)
 inv=g.copy();inv['on_hand']=np.where((inv.eid+inv.day)%17==0,0,(inv.eid*5+inv.day*3)%65)
 cap=rg.copy();cap['available']=120.+(cap.region*7+cap.day*3)%50
 weather=rg.copy();weather['temp']=18.+np.sin(weather.day/13+weather.region)*9
 price=sg.copy();price['price']=8.+price.sector*2+np.sin(price.day/9)*.5
 fx=rg.copy();fx['rate']=.8+fx.region*.12+np.sin(fx.day/21)*.03
 target=pd.MultiIndex.from_product([range(5),range(7)],names=['sector','weekday']).to_frame(index=False);target['target']=25.+target.sector*3+target.weekday
 policies=pd.DataFrame([(e,start,start+40,float(600+e%17*20+start*2)) for e in eid for start in range(0,160,40)],columns=['eid','valid_from','valid_to','budget'])
 edges=pd.DataFrame([(e,int((e+q-1)%128+1),float(.3+q*.11)) for e in eid for q in [1,7,19]],columns=['src','dst','weight'])
 return dict(entities=ent,calendar=cal,measurements=m,trades=t,reversals=rev,orders=o,shipments=pd.DataFrame(shipments,columns=['sid','oid','day','qty']),inventory=inv,capacity=cap,weather=weather,prices=price,fx=fx,targets=target,outages=pd.DataFrame(outages,columns=['qid','eid','start_day','end_day','severity']),policies=policies,interventions=pd.DataFrame(interventions,columns=['eid','day','effect']),events=ev,edges=edges)

def connect(database=DB):
 return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database=database,autocommit=True,connect_timeout=10,read_timeout=180,write_timeout=60)
def engine():
 return create_engine(URL.create('mysql+pymysql',username=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),database=DB),connect_args=dict(connect_timeout=10,read_timeout=180,write_timeout=60),pool_size=1,max_overflow=0)
def reference_sql(sql):
 # DuckDB 1.3.2 eagerly inlines single-use CTEs; repeated nonlinear score
 # references can expand exponentially. These optimizer hints change no rows,
 # frames or arithmetic and are NEVER sent to MatrixOne.
 return re.sub(r'\b(layer\d+_(?:windows|score)) AS \(',r'\1 AS MATERIALIZED (',sql)
class Reference:
 def __init__(self,connection):self.connection=connection
 def execute(self,sql,*args):return self.connection.execute(reference_sql(sql),*args)
 def executemany(self,*args):return self.connection.executemany(*args)
 def close(self):return self.connection.close()
def oracle(data):
 db=duckdb.connect(config={'threads':1})
 for name,df in data.items():
  db.register('incoming',df);db.execute(f'CREATE TABLE {name} AS SELECT * FROM incoming');db.unregister('incoming')
 return Reference(db)
def read(c,sql):
 with c.cursor() as q:q.execute(sql);return pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
def compare(a,b,tol=1e-7):
 assert list(a)==list(b) and a.shape==b.shape,dict(expected_shape=a.shape,actual_shape=b.shape,expected_columns=list(a),actual_columns=list(b))
 x=a.to_numpy(float);y=b.to_numpy(float);good=np.isclose(x,y,rtol=tol,atol=tol,equal_nan=True)
 if not good.all():
  r,col=np.argwhere(~good)[0];raise AssertionError(dict(row=int(r),column=a.columns[col],expected=float(x[r,col]),actual=float(y[r,col]),max_abs=float(np.nanmax(np.abs(x-y)))))
 # Integer-valued columns are compared exactly, with exact null-position agreement.
 for col in a:
  xx=pd.to_numeric(a[col]).to_numpy(float);yy=pd.to_numeric(b[col]).to_numpy(float)
  if col in ['eid','day','event_id','minute','rn','session_id','island_id','bucket','observations','n','late_count','null_count']:
   assert np.array_equal(xx,yy,equal_nan=True),(col,'integer/null mismatch')
def audit(data,tag):
 c=connect();out={}
 for n,f in data.items():
  a=read(c,f'SELECT * FROM `{n}`').sort_values(list(f)).reset_index(drop=True);b=f.sort_values(list(f)).reset_index(drop=True);compare(b,a,1e-12);out[n]=dict(rows=len(a),sha256=hashlib.sha256(a.to_numpy('<f8').tobytes()).hexdigest())
 c.close();(ROOT/f'source-audit-{tag}.json').write_text(json.dumps(out,indent=2));return out
def setup(data):
 c=connect(None)
 with c.cursor() as q:
  q.execute(f'CREATE DATABASE IF NOT EXISTS `{DB}`');q.execute(f'USE `{DB}`')
  for n,f in data.items():
   q.execute(f'CREATE TABLE IF NOT EXISTS `{n}`({SCHEMAS[n]})');q.execute(f'SELECT COUNT(*) FROM `{n}`');count=q.fetchone()[0]
   if count==0:
    rows=[tuple(None if pd.isna(v) else v.item() if isinstance(v,np.generic) else v for v in row) for row in f.itertuples(index=False,name=None)]
    for k in range(0,len(rows),512):q.executemany(f'INSERT INTO `{n}` VALUES({",".join(["%s"]*len(f.columns))})',rows[k:k+512])
   else:assert count==len(f),(n,count,len(f))
 c.close();manifest=dict(seed=SEED,database=DB,schemas=SCHEMAS,rows={n:len(f) for n,f in data.items()},time_encoding='Integer UTC epoch minutes; calendar offset change is synthetic, not a full IANA timezone implementation.')
 for n,f in data.items():f.to_csv(ROOT/'inputs'/f'{n}.csv.gz',index=False,float_format='%.17g',compression={'method':'gzip','mtime':0})
 (ROOT/'dataset.json').write_text(json.dumps(manifest,indent=2));return manifest
if __name__=='__main__':
 d=tables();print(setup(d),flush=True);print(audit(d,'before'),flush=True)
