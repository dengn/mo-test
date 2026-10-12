"""Independent synthetic business data; all clocks are UTC integer minutes/days."""
import hashlib,json,os,decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime,timedelta,timezone
import numpy as np,pandas as pd,pymysql,duckdb
from sqlalchemy import create_engine,URL
ROOT=Path(__file__).resolve().parent
DB=os.getenv('MO_NEEDS_DATABASE','ds_needs_20261012_r1')
SEED=20261012091
EPOCH=int(datetime(2024,10,15,tzinfo=timezone.utc).timestamp()//60)
SCHEMAS={
 'units':'uid INT PRIMARY KEY,region INT,sector INT,scale DOUBLE',
 'calendar':'day INT PRIMARY KEY,weekday INT,holiday INT,epoch_min BIGINT',
 'attrs':'aid INT PRIMARY KEY,uid INT,valid_from INT,valid_to INT,recorded_day INT,revision INT,scale DOUBLE,region INT',
 'observations':'rid INT PRIMARY KEY,event_id INT,uid INT,day INT,received_day INT,revision INT,valid INT,v DOUBLE',
 'labels':'lid INT PRIMARY KEY,uid INT,day INT,ready_day INT,y DOUBLE',
 'daily':'uid INT,day INT,signal DOUBLE,demand DOUBLE,price DOUBLE,weather DOUBLE',
 'subjects':'sid INT PRIMARY KEY,uid INT,segment INT,arm INT,propensity DOUBLE,age DOUBLE,pre DOUBLE',
 'outcomes':'oid INT PRIMARY KEY,sid INT,day INT,ready_day INT,y DOUBLE,converted INT',
 'conversions':'cid INT PRIMARY KEY,person INT,day INT,minute BIGINT,revenue DOUBLE,converted INT',
 'touches':'tid INT PRIMARY KEY,person INT,device INT,minute BIGINT,received_day INT,channel INT,score DOUBLE',
 'identities':'device INT,person INT,valid_from INT,valid_to INT,recorded_day INT',
 'campaigns':'channel INT PRIMARY KEY,spend DOUBLE,quality DOUBLE',
 'flows':'fid INT PRIMARY KEY,src INT,dst INT,day INT,minute BIGINT,amount DOUBLE,received_day INT',
 'gps':'pid INT PRIMARY KEY,uid INT,day INT,minute BIGINT,received_day INT,lat DOUBLE,lon DOUBLE,valid INT,offset_min INT,local_min BIGINT,fold INT',
 'fences':'fid INT PRIMARY KEY,region INT,x1 DOUBLE,x2 DOUBLE,y1 DOUBLE,y2 DOUBLE',
 'roads':'rid INT PRIMARY KEY,src INT,dst INT,distance DOUBLE,blocked_day INT',
 'predictions':'pid INT PRIMARY KEY,uid INT,day INT,model INT,segment INT,prob DOUBLE,label INT,ready_day INT,feature DOUBLE',
 'changes':'seq INT PRIMARY KEY,checkpoint INT,event_id INT,uid INT,day INT,v DOUBLE,op INT',
 'deliveries':'delivery_id INT PRIMARY KEY,event_id INT,uid INT,batch INT,event_min INT,v DOUBLE,kind INT',
}

def tables():
 rng=np.random.default_rng(SEED);uids=np.arange(1,33);days=np.arange(96)
 units=pd.DataFrame(dict(uid=uids,region=uids%4,sector=uids%5,scale=1+uids%7*.15))
 calendar=pd.DataFrame(dict(day=days,weekday=days%7,holiday=((days%17==0)|(days%23==0)).astype(int),epoch_min=EPOCH+days*1440))
 attrs=[];obs=[];labels=[];daily=[]
 for u in uids:
  for start,end in [(0,40),(40,70),(70,96)]:
   for rev in [0,1]:attrs.append((len(attrs)+1,int(u),start,end,start+(2 if not rev else 6)+u%3,rev,float(1+u%7*.15+rev*.08),int(u%4)))
  for day in days:
   base=20+u%9+.09*day+3*np.sin((day+u)/7)+.8*(day%7)+float(rng.normal(0,.4))
   demand=30+u%11+.12*day+5*np.sin(day/7)+int(day%17==0)*8+(3 if day>=60 else 0)
   price=float(20+u%7+.025*day+np.sin(day/8+u)*.6)
   daily.append((int(u),int(day),float(base),float(demand),price,float(15+np.cos(day/11+u%4)*6)))
   labels.append((len(labels)+1,int(u),int(day),int(day+1+u%3),float(demand+rng.normal(0,.6))))
   for tick in range(1+int((u+day)%4==0)):
    eid=int(u*10000+day*2+tick)
    for rev in [0,1]:
     value=base+tick*.2+rev*float(np.sin(u+day)*.7)
     if (u+day+tick)%19==0:value=np.nan
     obs.append((len(obs)+1,eid,int(u),int(day),int(day+tick+rev*(1+(u+day)%5)),rev,int(not(rev and (u+day)%31==0)),float(value)))
 subjects=[];outcomes=[]
 for sid in range(1,769):
  uid=1+(sid-1)%32;segment=sid%4;pre=float(12+segment*2+rng.normal(0,2));prop=float(.2+.6/(1+np.exp(-(pre-15)/3)))
  arm=int(rng.random()<(.5 if sid<=384 else prop));subjects.append((sid,uid,segment,arm,prop,float(20+sid%45),pre))
  for day in range(8,57):
   effect=0 if day<32 else arm*(1.5+segment*.35)
   y=pre+.07*day+np.sin(day/5)*.4+effect+float(rng.normal(0,.8));outcomes.append((len(outcomes)+1,sid,day,day+sid%3,float(y),int(y>17)))
 conversions=[];touches=[];ident=[]
 for person in range(1,97):
  for device in [person*2,person*2+1]:ident.append((device,person,0,96,person%5))
  for day in range(10,90,4):
   minute=EPOCH+day*1440+(person*13)%180;revenue=float(10+(person*7+day)%90);converted=int((person+day)%5!=0)
   conversions.append((len(conversions)+1,person,day,minute,revenue,converted))
   for k in range((person+day)%5):
    tm=minute-(1+k)*420-(person%3)*60;channel=(person+day+k)%6
    touches.append((len(touches)+1,person,person*2+k%2,tm,int((tm-EPOCH)//1440+k%2),channel,float(.1+.08*channel)))
   # A post-conversion touch must never receive credit for this conversion.
   touches.append((len(touches)+1,person,person*2,minute+30,day,5,.5))
 flows=[];gps=[];roads=[]
 zones={0:'UTC',1:'Asia/Shanghai',2:'America/New_York',3:'Europe/London'}
 centers={0:(31.,121.),1:(31.1,121.1),2:(40.7,-74.),3:(51.5,-.1)}
 for u in uids:
  for q in [1,2,7]:roads.append((len(roads)+1,int(u),int((u+q-1)%32+1),float(1+q*.8+u%5*.12),int(40+(u+q)%20)))
  for day in range(8,90):
   for q in [1,2,7]:flows.append((len(flows)+1,int(u),int((u+q-1)%32+1),day,EPOCH+day*1440+int(u*5+q),float(5+(u*3+day*7+q)%80),day+(u+q)%3))
   lat0,lon0=centers[int(u%4)]
   for tick in range(4):
    minute=EPOCH+day*1440+int(60+tick*35+u%3*7)
    lat=float(lat0+.015*np.sin((day+u+tick)/4));lon=float(lon0+.015*np.cos((day+u+tick)/5))
    if u>=31:lat=10.+tick*.01;lon=179.8 if tick%2==0 else -179.9
    valid=int((u+day+tick)%37!=0)
    if not valid:lat=np.nan
    tz=ZoneInfo(zones[int(u%4)]);dt=datetime.fromtimestamp(minute*60,timezone.utc).astimezone(tz);offset=int(dt.utcoffset().total_seconds()//60)
    gps.append((len(gps)+1,int(u),day,minute,day+tick%2,lat,lon,valid,offset,minute+offset,int(dt.fold)))
 for day in range(8,90):
  for root in [1,9,17,25]:
   for k,(src,dst) in enumerate([(root,root+1),(root+1,root+2),(root+2,root)]):flows.append((len(flows)+1,src,dst,day,EPOCH+day*1440+400+k*20,float(50-k*2),day))
 fences=[]
 for region,(lat,lon) in centers.items():
  for k in range(2):fences.append((len(fences)+1,region,lon-.01+k*.005,lon+.01+k*.005,lat-.01+k*.005,lat+.01+k*.005))
 # Exact fence-boundary points, and both occurrences of a DST fall-back clock.
 for region in range(4):
  uid=4 if region==0 else region;f=fences[region*2];minute=EPOCH+35*1440
  tz=ZoneInfo(zones[region]);dt=datetime.fromtimestamp(minute*60,timezone.utc).astimezone(tz);offset=int(dt.utcoffset().total_seconds()//60)
  gps.append((len(gps)+1,uid,35,minute,35,float(f[5]),float(f[3]),1,offset,minute+offset,int(dt.fold)))
 for stamp in ['2024-11-03T05:30:00+00:00','2024-11-03T06:30:00+00:00']:
  dt=datetime.fromisoformat(stamp);minute=int(dt.timestamp()//60);local=dt.astimezone(ZoneInfo('America/New_York'));offset=int(local.utcoffset().total_seconds()//60)
  gps.append((len(gps)+1,2,int((minute-EPOCH)//1440),minute,int((minute-EPOCH)//1440),40.7,-74.,1,offset,minute+offset,int(local.fold)))
 predictions=[]
 for u in uids:
  for day in range(8,90):
   for model in [0,1]:
    feature=float(rng.normal((.7 if day>=60 else 0)+u%4*.2,1));latent=float(feature*.7+.2*(u%4)+.2*np.sin(day/8));prob=float(1/(1+np.exp(-(latent+model*.15))))
    if (u+day)%41==0:prob=float((u+day)%2)
    label=int(rng.random()<1/(1+np.exp(-latent)));predictions.append((len(predictions)+1,int(u),day,model,int(u%4),prob,label,day+1+(u+day)%6,feature))
 changes=[]
 for event in range(1,801):
  uid=1+(event-1)%32;day=8+(event*7)%64;v=float(2+(event*13)%31)
  changes.append((len(changes)+1,0,event,uid,day,v,1))
 for cp in range(1,10):
  for k in range(72):
   event=1+(cp*67+k*11)%800;uid=1+(event-1)%32;day=8+(event*7+int(k%9==0))%64;op=0 if k%11==0 else 1
   changes.append((len(changes)+1,cp,event,uid,day,float(3+(event*13+cp)%37),op))
  for k in range(8):
   event=800+cp*8+k;changes.append((len(changes)+1,cp,event,1+event%32,8+(event*7)%64,float(4+event%29),1))
 deliveries=[]
 for batch in range(10):
  for k in range(96):
   uid=1+k%32;eid=batch*1000+k;ts=batch*10+(k%7)
   if k%13==0 and batch>1:ts-=30
   deliveries.append((len(deliveries)+1,eid,uid,batch,ts,float(2+(batch*7+k)%23),k%4))
   if k%17==0:deliveries.append((len(deliveries)+1,eid,uid,batch,ts,float(2+(batch*7+k)%23),k%4))
 def frame(rows,cols):return pd.DataFrame(rows,columns=cols.split())
 return dict(units=units,calendar=calendar,attrs=frame(attrs,'aid uid valid_from valid_to recorded_day revision scale region'),observations=frame(obs,'rid event_id uid day received_day revision valid v'),labels=frame(labels,'lid uid day ready_day y'),daily=frame(daily,'uid day signal demand price weather'),subjects=frame(subjects,'sid uid segment arm propensity age pre'),outcomes=frame(outcomes,'oid sid day ready_day y converted'),conversions=frame(conversions,'cid person day minute revenue converted'),touches=frame(touches,'tid person device minute received_day channel score'),identities=frame(ident,'device person valid_from valid_to recorded_day'),campaigns=frame([(c,float(100+c*30),float(.1+.08*c)) for c in range(6)],'channel spend quality'),flows=frame(flows,'fid src dst day minute amount received_day'),gps=frame(gps,'pid uid day minute received_day lat lon valid offset_min local_min fold'),fences=frame(fences,'fid region x1 x2 y1 y2'),roads=frame(roads,'rid src dst distance blocked_day'),predictions=frame(predictions,'pid uid day model segment prob label ready_day feature'),changes=frame(changes,'seq checkpoint event_id uid day v op'),deliveries=frame(deliveries,'delivery_id event_id uid batch event_min v kind'))

def connect(database=DB):
 return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database=database,autocommit=True,connect_timeout=10,read_timeout=90,write_timeout=60)
def engine():return create_engine(URL.create('mysql+pymysql',username=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),database=DB),connect_args={'read_timeout':90},pool_size=1,max_overflow=0)
def read(c,sql):
 with c.cursor() as q:q.execute(sql);return pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
def plain(x):
 if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
 if isinstance(x,np.generic):x=x.item()
 if isinstance(x,decimal.Decimal):x=float(x)
 if isinstance(x,float) and not np.isfinite(x):return None
 return x
def values(df):return plain(df.to_numpy())
EXACT={'uid','id','sid','day','pid','event_id','received_day','revision','valid','aid','recorded_day','region','segment','arm','cid','person','converted','tid','minute','channel','fid','src','dst','event_min','batch','kind','epoch_min','offset_min','local_min','fold','model','known','n','count','hops','code','checkpoint','case_id','key','window_start','window_end','n_valid','grid_x','grid_y','session_id','node','max_received','max_revision','raw_n'}
def compare(g,a,tol=1e-7):
 assert list(g)==list(a) and g.shape==a.shape,dict(expected_shape=g.shape,actual_shape=a.shape,expected_columns=list(g),actual_columns=list(a))
 for col in g:
  if pd.api.types.is_numeric_dtype(g[col]) or all(x is None or isinstance(x,(int,float,np.number,decimal.Decimal)) for x in g[col]):
   x=pd.to_numeric(g[col]).to_numpy(float);y=pd.to_numeric(a[col]).to_numpy(float)
   if col in EXACT or col.endswith(('_day','_min','_id','_count')) or col.startswith('n_'):assert np.array_equal(x,y,equal_nan=True),(col,'exact mismatch')
   else:np.testing.assert_allclose(y,x,rtol=tol,atol=tol,equal_nan=True,err_msg=col)
  else:assert [None if pd.isna(x) else str(x) for x in g[col]]==[None if pd.isna(x) else str(x) for x in a[col]],col

def oracle(data):
 d=duckdb.connect(config={'threads':1})
 for name,df in data.items():d.register('source',df);d.execute(f'CREATE TABLE {name} AS SELECT * FROM source');d.unregister('source')
 return d

def setup(data):
 c=connect(None)
 with c.cursor() as q:q.execute(f'CREATE DATABASE IF NOT EXISTS `{DB}`')
 c.close();c=connect()
 for name,df in data.items():
  with c.cursor() as q:
   q.execute(f'CREATE TABLE IF NOT EXISTS `{name}`({SCHEMAS[name]})');q.execute(f'SELECT COUNT(*) FROM `{name}`');assert q.fetchone()[0]==0,('Refusing to overwrite source table',name)
   placeholders=','.join(['%s']*len(df.columns));rows=[tuple(None if pd.isna(v) else v.item() if isinstance(v,np.generic) else v for v in row) for row in df.itertuples(index=False,name=None)]
   for k in range(0,len(rows),512):q.executemany(f'INSERT INTO `{name}` VALUES({placeholders})',rows[k:k+512])
  df.to_csv(ROOT/'inputs'/f'{name}.csv.gz',index=False,float_format='%.17g',compression={'method':'gzip','mtime':0})
  print('Loaded',name,len(df),flush=True)
 c.close()

def audit(data,tag):
 c=connect();result={}
 for name,g in data.items():
  g=g.sort_values(list(g)).reset_index(drop=True);a=read(c,f'SELECT * FROM `{name}`').sort_values(list(g)).reset_index(drop=True);compare(g,a,1e-12)
  b=json.dumps(values(a),separators=(',',':'),allow_nan=False).encode();result[name]=dict(rows=len(a),sha256=hashlib.sha256(b).hexdigest())
 c.close();(ROOT/f'source-audit-{tag}.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 d=tables();setup(d);audit(d,'before');(ROOT/'fixtures.json').write_text(json.dumps(dict(seed=SEED,rows={k:len(v) for k,v in d.items()},schemas=SCHEMAS),indent=2))
