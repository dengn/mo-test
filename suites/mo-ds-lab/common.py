import datetime as dt
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pymysql
from sqlalchemy import URL, create_engine

ROOT = Path(__file__).resolve().parent
DATABASE = os.getenv('MO_DATABASE', 'ds_validation_20261011')
SEED = 20261011

def connection(database=DATABASE):
    return pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),
        port=int(os.getenv('MO_PORT','6001')), user=os.getenv('MO_USER','root'),
        password=os.getenv('MO_PASSWORD','111'), database=database,
        autocommit=True, connect_timeout=10, read_timeout=30, write_timeout=30)

def engine():
    return create_engine(URL.create('mysql+pymysql', username=os.getenv('MO_USER','root'),
        password=os.getenv('MO_PASSWORD','111'), host=os.getenv('MO_HOST','127.0.0.1'),
        port=int(os.getenv('MO_PORT','6001')), database=DATABASE),
        connect_args={'connect_timeout':10,'read_timeout':30,'write_timeout':30},
        pool_size=1, max_overflow=0)

def dataset():
    i=np.arange(8192,dtype=np.int64)
    x=np.round(np.sin(i*.173)*100+i%13,3)
    y=np.round(np.cos(i*.113)*50+i%7,3)
    nx=x.copy(); nx[i%11==0]=np.nan
    txt=np.array(['数据🚀' if j%7==0 else f'cat_{j%23}' for j in i])
    ts=pd.to_datetime('2024-01-01')+pd.to_timedelta(i*37,unit='m')
    return pd.DataFrame({'id':i,'g':i%17,'x':x,'y':y,'nx':nx,
        'k':(i*29)%101-50,'txt':txt,'ts':ts,
        'js':[json.dumps({'v':int(j%101)}) for j in i]})

def plain(v):
    if v is None: return None
    if isinstance(v,(np.integer,np.floating)): v=v.item()
    if isinstance(v,float) and not math.isfinite(v): return None
    return v

def equal(a,b):
    a,b=plain(a),plain(b)
    if a is None or b is None: return a is None and b is None
    try: return math.isclose(float(a),float(b),rel_tol=1e-7,abs_tol=1e-7)
    except (ValueError,TypeError): return a==b

def setup():
    c=connection(None)
    with c.cursor() as q:
        q.execute(f'CREATE DATABASE IF NOT EXISTS `{DATABASE}`')
        q.execute(f'USE `{DATABASE}`')
        q.execute('CREATE TABLE IF NOT EXISTS ds (id BIGINT PRIMARY KEY,g INT,x DOUBLE,y DOUBLE,nx DOUBLE,k INT,txt VARCHAR(64),ts DATETIME,js JSON)')
        q.execute('SELECT COUNT(*) FROM ds')
        count=q.fetchone()[0]
        if count==0:
            d=dataset()
            rows=[tuple(None if isinstance(v,float) and np.isnan(v) else
                v.to_pydatetime() if isinstance(v,pd.Timestamp) else
                v.item() if isinstance(v,np.generic) else v for v in r)
                for r in d.itertuples(index=False,name=None)]
            for j in range(0,len(rows),512):
                q.executemany('INSERT INTO ds VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',rows[j:j+512])
        elif count!=8192:
            raise RuntimeError(f'Unexpected ds row count {count}; refusing to reuse')
        q.execute('CREATE TABLE IF NOT EXISTS connector_input (id BIGINT PRIMARY KEY,cid INT,x DOUBLE,y DOUBLE,nx DOUBLE,k INT)')
        q.execute('SELECT COUNT(*) FROM connector_input')
        count=q.fetchone()[0]
        if count==0:
            d=dataset().iloc[:6400].copy(); d['cid']=d.id%100
            rows=[(int(r.id),int(r.cid),float(r.x),float(r.y),None if pd.isna(r.nx) else float(r.nx),int(r.k)) for r in d.itertuples()]
            for j in range(0,len(rows),512):
                q.executemany('INSERT INTO connector_input VALUES (%s,%s,%s,%s,%s,%s)',rows[j:j+512])
        elif count!=6400: raise RuntimeError('Unexpected connector_input contents')
        q.execute('SELECT version()'); version=q.fetchone()[0]
    c.close()
    return version

CONNECTOR_AGGS = {
    'count':'COUNT(*)', 'sum':'SUM(x)', 'mean':'AVG(x)', 'min':'MIN(x)',
    'max':'MAX(x)', 'variance':'VAR_POP(x)', 'stddev':'STDDEV_POP(x)',
    'dot':'SUM(x*y)', 'coalesce':'SUM(COALESCE(nx,0))',
    'positive':'SUM(CASE WHEN x>0 THEN 1 ELSE 0 END)',
}

def connector_expected(name,cid):
    d=dataset().iloc[:6400]; a=d[d.id%100==cid]
    return plain({'count':lambda:len(a),'sum':lambda:a.x.sum(),
        'mean':lambda:a.x.mean(),'min':lambda:a.x.min(),'max':lambda:a.x.max(),
        'variance':lambda:a.x.var(ddof=0),'stddev':lambda:a.x.std(ddof=0),
        'dot':lambda:np.dot(a.x,a.y),'coalesce':lambda:a.nx.fillna(0).sum(),
        'positive':lambda:(a.x>0).sum()}[name]())
