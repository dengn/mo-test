"""Deterministic synthetic multi-table analytics data; no production data used."""
import hashlib
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pymysql
from sqlalchemy import URL,create_engine

ROOT=Path(__file__).resolve().parent
DB=os.getenv('MO_LONG_DATABASE','ds_long_20261011')
SEED=2026101102

def connect(database=DB):
    return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),
        user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database=database,
        autocommit=True,connect_timeout=10,read_timeout=60,write_timeout=60)

def engine():
    return create_engine(URL.create('mysql+pymysql',username=os.getenv('MO_USER','root'),
        password=os.getenv('MO_PASSWORD','111'),host=os.getenv('MO_HOST','127.0.0.1'),
        port=int(os.getenv('MO_PORT','6001')),database=DB),
        connect_args={'connect_timeout':10,'read_timeout':60,'write_timeout':60},pool_size=1,max_overflow=0)

SCHEMAS={
 'customers':'cid INT PRIMARY KEY,region INT,tier INT,signup INT,credit DOUBLE',
 'products':'pid INT PRIMARY KEY,category INT,price DOUBLE',
 'orders':'oid INT PRIMARY KEY,cid INT,day INT,amount DOUBLE,cost DOUBLE,cancelled INT,channel INT,ts DATETIME',
 'items':'iid INT PRIMARY KEY,oid INT,pid INT,qty INT,price DOUBLE',
 'payments':'payid INT PRIMARY KEY,oid INT,day INT,paid DOUBLE,success INT',
 'refunds':'rid INT PRIMARY KEY,oid INT,day INT,refunded DOUBLE,reason INT',
 'events':'eid INT PRIMARY KEY,cid INT,day INT,session_id INT,kind INT,value DOUBLE,ts DATETIME',
 'edges':'src INT,dst INT,weight DOUBLE',
 'calendar':'day INT PRIMARY KEY,week INT,weekday INT,date DATETIME',
 'market':'asset INT,day INT,close_price DOUBLE,volume DOUBLE',
 'inventory':'pid INT,day INT,on_hand INT,lead_days INT',
 'campaigns':'channel INT,day INT,spend DOUBLE,impressions INT',
 'subscriptions':'cid INT,month INT,billed DOUBLE,paid DOUBLE,active INT',
 'targets':'tier INT,week INT,revenue_target DOUBLE,risk_budget DOUBLE',
}

def tables():
    rng=np.random.default_rng(SEED)
    cid=np.arange(1,1201,dtype=np.int64)
    credit=np.round(rng.normal(80,20,len(cid)),4); credit[cid%11==0]=np.nan
    customers=pd.DataFrame({'cid':cid,'region':cid%5,'tier':cid%3,'signup':cid%10,'credit':credit})
    pid=np.arange(1,81,dtype=np.int64)
    products=pd.DataFrame({'pid':pid,'category':pid%8,'price':np.round(4+(pid*17)%90+.1234,4)})
    oid=np.arange(1,12001,dtype=np.int64)
    item_oid=np.repeat(oid,3)
    item_pid=(np.arange(len(item_oid))*19+item_oid*7)%80+1
    items=pd.DataFrame({'iid':np.arange(1,len(item_oid)+1,dtype=np.int64),'oid':item_oid,
        'pid':item_pid,'qty':rng.integers(1,5,len(item_oid)),
        'price':products.price.to_numpy()[item_pid-1]})
    customer=(oid*37)%1200+1
    # Last 24 customers have no purchases/events: left joins and empty partitions.
    customer=np.minimum(customer,1176)
    days=customer%10+1+(oid*17)%80
    amount=(items.price*items.qty).groupby(items.oid).sum().reindex(oid).to_numpy()
    orders=pd.DataFrame({'oid':oid,'cid':customer,'day':days,'amount':amount,
        'cost':np.round(amount*(.35+(oid%7)*.055),4),'cancelled':(oid%11==0).astype(np.int64),
        'channel':oid%4,'ts':pd.Timestamp('2024-01-01')+pd.to_timedelta(days,unit='D')+pd.to_timedelta(oid%24,unit='h')})
    poid=np.repeat(oid,2); attempt=np.tile([0,1],len(oid))
    payments=pd.DataFrame({'payid':np.arange(1,len(poid)+1,dtype=np.int64),'oid':poid,
        'day':np.repeat(days,len([0,1]))+attempt,
        'paid':np.repeat(amount,2)*np.where(attempt==0,.6,.4),
        'success':((poid%9!=0)|(attempt==1)).astype(np.int64)})
    chosen=oid[(oid%13==0)|(oid%17==0)]
    refunds=pd.DataFrame({'rid':np.arange(1,len(chosen)+1,dtype=np.int64),'oid':chosen,
        'day':days[chosen-1]+3,'refunded':amount[chosen-1]*np.where(chosen%13==0,.3,.5),'reason':chosen%4})
    ecid=np.repeat(np.arange(1,1177,dtype=np.int64),30)
    ei=np.arange(len(ecid),dtype=np.int64)
    eday=ecid%10+rng.integers(0,81,len(ecid))
    kind=(ei+ecid)%6
    # Three deterministic funnel events share each of ten sessions per customer.
    event=pd.DataFrame({'eid':ei+1,'cid':ecid,'day':eday,'session_id':ecid*100+ei%30//3,
        'kind':kind,'value':np.round(rng.normal(0,3,len(ecid)),4),
        'ts':pd.Timestamp('2024-01-01')+pd.to_timedelta(eday,unit='D')+pd.to_timedelta(ei%24,unit='h')})
    edges=pd.DataFrame({'src':np.repeat(cid,3),'dst':(np.arange(3600)*31+np.repeat(cid,3)*13)%1200+1,
        'weight':np.round(rng.uniform(.1,1,3600),5)})
    calendar=pd.DataFrame({'day':np.arange(96,dtype=np.int64),'week':np.arange(96)//7,
        'weekday':np.arange(96)%7,'date':pd.date_range('2024-01-01',periods=96)})
    market_asset=np.repeat(np.arange(8),365);market_day=np.tile(np.arange(365),8)
    market=pd.DataFrame({'asset':market_asset,'day':market_day,'close_price':np.round(50+market_asset*11+market_day*.025+np.sin(market_day/11+market_asset)*3+rng.normal(0,.25,len(market_day)),6),'volume':rng.uniform(1000,10000,len(market_day))})
    inv_pid=np.repeat(pid,96);inv_day=np.tile(np.arange(96),80)
    inventory=pd.DataFrame({'pid':inv_pid,'day':inv_day,'on_hand':(inv_pid*7+inv_day*13)%100,'lead_days':1+inv_pid%14})
    campaigns=pd.DataFrame({'channel':np.repeat(np.arange(4),96),'day':np.tile(np.arange(96),4),'spend':rng.uniform(20,800,384),'impressions':rng.integers(100,10000,384)})
    scid=np.repeat(cid,24);month=np.tile(np.arange(24),1200);bill=np.round(10+scid%31+month*.2,4)
    subscriptions=pd.DataFrame({'cid':scid,'month':month,'billed':bill,'paid':bill*np.where((scid+month)%13==0,.4,1),'active':((scid+month)%17!=0).astype(np.int64)})
    targets=pd.DataFrame({'tier':np.repeat(np.arange(3),14),'week':np.tile(np.arange(14),3),'revenue_target':rng.uniform(1000,10000,42),'risk_budget':rng.uniform(.1,.5,42)})
    return {'customers':customers,'products':products,'orders':orders,'items':items,
        'payments':payments,'refunds':refunds,'events':event,'edges':edges,'calendar':calendar,'market':market,'inventory':inventory,'campaigns':campaigns,'subscriptions':subscriptions,'targets':targets}

def local_oracle(data):
    db=duckdb.connect(config={'threads':1})
    for name,df in data.items():
        db.register('_incoming',df); db.execute(f'CREATE TABLE {name} AS SELECT * FROM _incoming'); db.unregister('_incoming')
    return db

def setup(data):
    c=connect(None)
    with c.cursor() as q:
        q.execute(f'CREATE DATABASE IF NOT EXISTS `{DB}`'); q.execute(f'USE `{DB}`')
        for name,df in data.items():
            q.execute(f'CREATE TABLE IF NOT EXISTS {name}({SCHEMAS[name]})')
            q.execute(f'SELECT COUNT(*) FROM {name}'); n=q.fetchone()[0]
            if n==0:
                rows=[]
                for row in df.itertuples(index=False,name=None):
                    rows.append(tuple(None if pd.isna(v) else v.to_pydatetime() if isinstance(v,pd.Timestamp)
                        else v.item() if isinstance(v,np.generic) else v for v in row))
                placeholders=','.join(['%s']*len(df.columns))
                for j in range(0,len(rows),512): q.executemany(f'INSERT INTO {name} VALUES({placeholders})',rows[j:j+512])
            elif n!=len(df): raise AssertionError(f'Unexpected existing {name} size {n}; use a new MO_COMPLEX_DATABASE')
    c.close()
    manifest={name:{'rows':len(df),'sha256':hashlib.sha256(df.to_csv(index=False,float_format='%.12g').encode()).hexdigest()} for name,df in data.items()}
    (ROOT/'dataset-manifest.json').write_text(json.dumps({'seed':SEED,'tables':manifest,'schema':SCHEMAS},indent=2))
    return manifest

def params(i):
    # One unique tuple per parameter index, with broad temporal/segment variation.
    lo=1+(i*7)%1150; hi=min(1201,lo+50+(i%19)*5)
    d0=(i*11)%55; d1=d0+12+(i%17)
    return dict(lo=lo,hi=hi,d0=d0,d1=d1,r=i%5,k=2+i%7,
        threshold=round(100+(i%41)*23.125,3),alpha=round(.01+(i%13)*.015,5),
        start=f"2024-{1+d0//31:02d}-{1+d0%28:02d}")

BASE='''WITH scope AS (SELECT * FROM customers WHERE cid>={lo} AND cid<{hi} AND region<>{r}),
oo AS (SELECT o.* FROM orders o JOIN scope c ON o.cid=c.cid WHERE o.day>={d0} AND o.day<{d1}),
ee AS (SELECT e.* FROM events e JOIN scope c ON e.cid=c.cid WHERE e.day>={d0} AND e.day<{d1})'''
