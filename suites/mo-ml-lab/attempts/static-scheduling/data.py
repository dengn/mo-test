"""Synthetic multi-source, temporally versioned ML fixture. No production data."""
import hashlib,json,os
from pathlib import Path
import numpy as np,pandas as pd,pymysql
ROOT=Path(__file__).resolve().parent
DB=os.getenv('MO_ML_DATABASE','ds_ml_20261011')
SEED=2026101107
SCHEMAS={
 'entities':'eid INT PRIMARY KEY,sector INT,region INT,bias DOUBLE',
 'readings':'eid INT,day INT,x0 DOUBLE,x1 DOUBLE,x2 DOUBLE,x3 DOUBLE',
 'targets':'eid INT,day INT,c0 DOUBLE,c1 DOUBLE,c2 DOUBLE,c3 DOUBLE',
 'trades':'tid INT,eid INT,day INT,amount DOUBLE,valid INT',
 'maintenance':'eid INT,day INT,score DOUBLE',
 'outages':'eid INT,day INT,minutes DOUBLE',
 'weather':'region INT,day INT,temp DOUBLE',
 'calendar':'day INT PRIMARY KEY,weekday INT',
 'prices':'sector INT,day INT,price DOUBLE',
 'exposures':'eid INT,sector INT,weight DOUBLE',
 'segments':'sector INT PRIMARY KEY,multiplier DOUBLE',
 'policies':'region INT PRIMARY KEY,cap DOUBLE',
 'events':'eid INT,day INT,kind INT,value DOUBLE',
 'interventions':'eid INT,day INT,active INT',
 'edges':'src INT,dst INT,weight DOUBLE',
 'labels':'eid INT,day INT,response DOUBLE,risk INT,anomaly INT',
}
def connect(database=DB):
 return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database=database,autocommit=True,connect_timeout=10,read_timeout=90,write_timeout=90)
def tables():
 r=np.random.default_rng(SEED);ids=np.arange(320);days=np.arange(80)
 eid=np.repeat(ids,80);day=np.tile(days,320);bias=r.normal(0,.7,320)
 phase=r.normal(0,.8,320);base=np.stack([np.sin(day/7+phase[eid])+bias[eid],np.cos(day/11+phase[eid])+bias[eid]*.2,day/80+bias[eid]*.4,np.sin(day/4+eid/23)*.5+np.cos(day/13)],1)
 clean=np.round(base,9);noisy=clean+r.normal(0,.12,clean.shape)
 anomaly=((eid*7+day*11)%47==0);noisy[anomaly,0]+=2.4
 noisy[(eid*13+day)%29==0,1]=np.nan
 readings=pd.DataFrame(dict(eid=eid,day=day,**{f'x{k}':noisy[:,k] for k in range(4)}))
 tar=pd.DataFrame(dict(eid=eid,day=day,**{f'c{k}':clean[:,k] for k in range(4)}))
 response=.8*clean[:,0]-.35*clean[:,1]+.25*clean[:,2]+.2*clean[:,0]*clean[:,3]+r.normal(0,.03,len(eid))
 risk=(clean[:,0]+.3*clean[:,2]+.1*(eid%5)>1.0).astype(int)
 te=np.repeat(eid,2);td=np.repeat(day,2);ti=np.arange(len(te))
 me=np.repeat(ids,10);md=np.tile(np.arange(0,80,8),320)
 oe=eid[(eid+day)%31==0];od=day[(eid+day)%31==0]
 ev=eid[(eid*3+day)%5==0];ed=day[(eid*3+day)%5==0]
 ex=np.repeat(ids,2);sec=(ex+np.tile([0,3],320))%8
 src=np.repeat(ids,3);dst=(src+np.tile([1,5,11],320))%320
 return {
 'entities':pd.DataFrame(dict(eid=ids,sector=ids%8,region=ids%5,bias=bias)),
 'readings':readings,'targets':tar,
 'trades':pd.DataFrame(dict(tid=ti,eid=te,day=td,amount=(np.repeat(clean[:,0],2)+3)*(1+ti%3),valid=(ti%7!=0).astype(int))),
 'maintenance':pd.DataFrame(dict(eid=me,day=md,score=.5+.2*np.sin(md/9+me/13))),
 'outages':pd.DataFrame(dict(eid=oe,day=od,minutes=1+(oe*7+od)%17)),
 'weather':pd.DataFrame(dict(region=np.repeat(np.arange(5),80),day=np.tile(days,5),temp=20+np.tile(np.sin(days/8),5)*8+np.repeat(np.arange(5),80))),
 'calendar':pd.DataFrame(dict(day=days,weekday=days%7)),
 'prices':pd.DataFrame(dict(sector=np.repeat(np.arange(8),80),day=np.tile(days,8),price=10+np.repeat(np.arange(8),80)+np.tile(days,8)*.02)),
 'exposures':pd.DataFrame(dict(eid=ex,sector=sec,weight=np.tile([.6,.4],320))),
 'segments':pd.DataFrame(dict(sector=np.arange(8),multiplier=1+np.arange(8)*.1)),
 'policies':pd.DataFrame(dict(region=np.arange(5),cap=2+np.arange(5)*.2)),
 'events':pd.DataFrame(dict(eid=ev,day=ed,kind=(ev+ed)%3,value=np.sin(ev/11+ed/5))),
 'interventions':pd.DataFrame(dict(eid=eid[(eid+day)%13==0],day=day[(eid+day)%13==0],active=1)),
 'edges':pd.DataFrame(dict(src=src,dst=dst,weight=np.tile([.5,.3,.2],320))),
 'labels':pd.DataFrame(dict(eid=eid,day=day,response=response,risk=risk,anomaly=anomaly.astype(int))),
 }
def params(i):
 return dict(i=i,lo=(i*17)%257,n=64,cut=32+(i*7)%36,horizon=1+i%4,length=6+2*(i%4),missing=i%5,noise=(i%7)*.025,hidden=8+4*(i%4),depth=2+i%4,epochs=8+i%7,lr=.004+.002*(i%5),l2=(i%4)*.0001,clip=.7+.2*(i%5),batch=16 if i%2 else 40)
def query(i):
 p=params(i);lo=p['lo'];hi=lo+64;cut=p['cut'];h=p['horizon'];L=p['length']
 return f'''WITH scope AS (
 SELECT e.*,CASE WHEN e.eid<{lo+40} THEN 0 WHEN e.eid<{lo+52} THEN 1 ELSE 2 END AS split_id,
 CASE WHEN e.eid<{lo+40} THEN {cut-2*h-2} WHEN e.eid<{lo+52} THEN {cut-h-1} ELSE {cut} END AS anchor FROM entities e WHERE e.eid>={lo} AND e.eid<{hi}),
 ts AS (SELECT t.eid,t.day,SUM(t.amount) AS amt FROM trades t JOIN scope s ON s.eid=t.eid WHERE t.valid=1 AND t.day<=s.anchor GROUP BY t.eid,t.day),
 es AS (SELECT v.eid,v.day,SUM(v.value) AS ev FROM events v JOIN scope s ON s.eid=v.eid WHERE v.day<=s.anchor AND NOT EXISTS(SELECT 1 FROM interventions z WHERE z.eid=v.eid AND z.day=v.day AND z.active=1) GROUP BY v.eid,v.day),
 ms AS (SELECT s.eid,MAX(m.day) AS md FROM scope s LEFT JOIN maintenance m ON m.eid=s.eid AND m.day<=s.anchor GROUP BY s.eid),
 ex AS (SELECT x.eid,SUM(x.weight*g.multiplier) AS exposure FROM exposures x JOIN segments g ON g.sector=x.sector GROUP BY x.eid),
 gr AS (SELECT a.src,SUM(a.weight) AS degree FROM edges a JOIN scope s ON s.eid=a.src JOIN scope d ON d.eid=a.dst AND d.split_id=s.split_id GROUP BY a.src),
 hist AS (SELECT s.eid,s.split_id,s.anchor,r.day,r.x0,r.x1,r.x2,r.x3,COALESCE(LAG(r.x0) OVER(PARTITION BY s.eid ORDER BY r.day),r.x0) AS lag0
 FROM scope s JOIN readings r ON r.eid=s.eid AND r.day>s.anchor-{L} AND r.day<=s.anchor)
 SELECT a.eid,a.split_id,a.anchor,a.day,a.x0,a.x1,a.x2,a.x3,a.lag0,
 COALESCE(t.amt,0) AS amt,COALESCE(v.ev,0) AS ev,COALESCE(m.score,0) AS maintenance,
 COALESCE(o.minutes,0) AS outage,w.temp,c.weekday,p.price,x.exposure,z.cap,COALESCE(g.degree,0) AS degree,
 e.bias,e.sector,e.region,lb.response,lb.risk,lbc.anomaly,cl.c0,cl.c1,cl.c2,cl.c3
 FROM hist a JOIN scope e ON e.eid=a.eid LEFT JOIN ts t ON t.eid=a.eid AND t.day=a.day
 LEFT JOIN es v ON v.eid=a.eid AND v.day=a.day LEFT JOIN ms ON ms.eid=a.eid LEFT JOIN maintenance m ON m.eid=ms.eid AND m.day=ms.md
 LEFT JOIN outages o ON o.eid=a.eid AND o.day=a.day JOIN weather w ON w.region=e.region AND w.day=a.day
 JOIN calendar c ON c.day=a.day JOIN prices p ON p.sector=e.sector AND p.day=a.day JOIN ex x ON x.eid=a.eid
 JOIN policies z ON z.region=e.region LEFT JOIN gr g ON g.src=a.eid
 JOIN labels lb ON lb.eid=a.eid AND lb.day=a.anchor+{h} JOIN labels lbc ON lbc.eid=a.eid AND lbc.day=a.anchor JOIN targets cl ON cl.eid=a.eid AND cl.day=a.anchor
 ORDER BY a.eid,a.day'''
def native(data,i):
 p=params(i);lo=p['lo'];h=p['horizon'];s=data['entities'].query('@lo<=eid<@lo+64').copy()
 s['split_id']=np.where(s.eid<lo+40,0,np.where(s.eid<lo+52,1,2));s['anchor']=np.where(s.split_id==0,p['cut']-2*h-2,np.where(s.split_id==1,p['cut']-h-1,p['cut']))
 a=s.merge(data['readings'],on='eid',validate='1:m');a=a[(a.day>a.anchor-p['length'])&(a.day<=a.anchor)].sort_values(['eid','day']);a['lag0']=a.groupby('eid').x0.shift().fillna(a.x0)
 t=data['trades'].merge(s[['eid','anchor']],on='eid');t=t[(t.valid==1)&(t.day<=t.anchor)].groupby(['eid','day']).amount.sum().rename('amt').reset_index()
 v=data['events'].merge(s[['eid','anchor']],on='eid');iv=data['interventions'];v=v.merge(iv,on=['eid','day'],how='left');v=v[(v.day<=v.anchor)&(v.active.isna())].groupby(['eid','day']).value.sum().rename('ev').reset_index()
 m=data['maintenance'].merge(s[['eid','anchor']],on='eid');m=m[m.day<=m.anchor].sort_values('day').drop_duplicates('eid',keep='last')[['eid','score']].rename(columns={'score':'maintenance'})
 ex=data['exposures'].merge(data['segments'],on='sector');ex['exposure']=ex.weight*ex.multiplier;ex=ex.groupby('eid').exposure.sum().reset_index()
 g=data['edges'].merge(s[['eid','split_id']],left_on='src',right_on='eid').merge(s[['eid','split_id']],left_on='dst',right_on='eid',suffixes=('_src','_dst'));g=g[g.split_id_src==g.split_id_dst].groupby('src').weight.sum().rename('degree').reset_index().rename(columns={'src':'eid'})
 a=a.merge(t,on=['eid','day'],how='left',validate='1:1').merge(v,on=['eid','day'],how='left',validate='1:1').merge(m,on='eid',how='left',validate='m:1').merge(data['outages'].rename(columns={'minutes':'outage'}),on=['eid','day'],how='left',validate='1:1')
 for k in ['amt','ev','maintenance','outage']:a[k]=a[k].fillna(0.)
 a=a.merge(data['weather'],on=['region','day'],validate='m:1').merge(data['calendar'],on='day',validate='m:1').merge(data['prices'],on=['sector','day'],validate='m:1').merge(ex,on='eid',validate='m:1').merge(data['policies'],on='region',validate='m:1').merge(g,on='eid',how='left',validate='m:1');a.degree=a.degree.fillna(0.)
 a['label_day']=a.anchor+h;a=a.merge(data['labels'],left_on=['eid','label_day'],right_on=['eid','day'],suffixes=('','_label'),validate='m:1').merge(data['targets'],left_on=['eid','anchor'],right_on=['eid','day'],suffixes=('','_clean'),validate='m:1')
 a=a.drop(columns=['anomaly']).merge(data['labels'][['eid','day','anomaly']],left_on=['eid','anchor'],right_on=['eid','day'],suffixes=('','_current'),validate='m:1')
 cols=['eid','split_id','anchor','day','x0','x1','x2','x3','lag0','amt','ev','maintenance','outage','temp','weekday','price','exposure','cap','degree','bias','sector','region','response','risk','anomaly','c0','c1','c2','c3']
 return a.sort_values(['eid','day'])[cols].reset_index(drop=True)
def read(c,sql):
 with c.cursor() as q:q.execute(sql);return pd.DataFrame(q.fetchall(),columns=[x[0] for x in q.description]).astype(float)
def compare(a,b,tol=1e-8):
 assert list(a)==list(b) and a.shape==b.shape,(a.shape,b.shape)
 x=a.to_numpy(float);y=b.to_numpy(float)
 if not np.allclose(x,y,rtol=tol,atol=tol,equal_nan=True):
  z=np.argwhere(~np.isclose(x,y,rtol=tol,atol=tol,equal_nan=True))[0];raise AssertionError((int(z[0]),a.columns[z[1]],x[tuple(z)],y[tuple(z)]))
def setup(d):
 c=connect(None)
 with c.cursor() as q:
  q.execute(f'CREATE DATABASE IF NOT EXISTS `{DB}`');q.execute(f'USE `{DB}`')
  for n,f in d.items():
   q.execute(f'CREATE TABLE IF NOT EXISTS `{n}`({SCHEMAS[n]})');q.execute(f'SELECT COUNT(*) FROM `{n}`');count=q.fetchone()[0]
   if not count:
    vals=[tuple(None if pd.isna(v) else v.item() if isinstance(v,np.generic) else v for v in row) for row in f.itertuples(index=False,name=None)]
    for k in range(0,len(vals),512):q.executemany(f'INSERT INTO `{n}` VALUES({",".join(["%s"]*len(f.columns))})',vals[k:k+512])
   else:assert count==len(f),(n,count,len(f))
 c.close()
 (ROOT/'dataset.json').write_text(json.dumps(dict(seed=SEED,database=DB,schemas=SCHEMAS,rows={n:len(f) for n,f in d.items()}),indent=2))
def audit(d,tag):
 c=connect();out={}
 for n,f in d.items():
  a=read(c,f'SELECT * FROM `{n}`').sort_values(list(f)).reset_index(drop=True);b=f.sort_values(list(f)).reset_index(drop=True).astype(float);compare(a,b,1e-12)
  out[n]={'rows':len(a),'sha256':hashlib.sha256(a.to_numpy('<f8').tobytes()).hexdigest()}
 c.close();(ROOT/f'source-audit-{tag}.json').write_text(json.dumps(out,indent=2));return out
if __name__=='__main__':
 d=tables();setup(d);audit(d,'before');c=connect()
 for i in [0,1,5,99,999]:a=read(c,query(i));b=native(d,i);compare(a,b);print(i,a.shape,flush=True)
 c.close()
