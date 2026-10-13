"""Owned GIS application databases and durable, inspectable workflow records."""
from pathlib import Path
import datetime
import decimal
import json
import os
import time
import traceback
import pymysql
import psycopg

P = Path(__file__).resolve().parent
MO_PORT = 6013
MO_COMMIT = 'fa7cc1d9b38e3324572a4efc5617033522de0cbf'
DB = 'gis_app_suite'

def connect(engine, db=DB):
    if engine in ('mo','mysql'):
        return pymysql.connect(host='127.0.0.1',port=MO_PORT if engine=='mo' else 63306,
            user='root',password='111' if engine=='mo' else '',database=db,
            autocommit=True,charset='utf8mb4',connect_timeout=5,read_timeout=45,write_timeout=45)
    return psycopg.connect(host='127.0.0.1',port=65432,user='gis',password='gis_local_test',
        dbname=db or 'gis',autocommit=True,connect_timeout=5)

def query(c,sql,args=None):
    with c.cursor() as q:
        q.execute(sql,args)
        return q.fetchall() if q.description else []

def norm(v):
    if isinstance(v,dict):return {k:norm(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [norm(x) for x in v]
    if isinstance(v,(datetime.datetime,datetime.date,datetime.time)):return v.isoformat()
    if isinstance(v,decimal.Decimal):return str(v)
    if isinstance(v,(bytes,memoryview)):return {'hex':bytes(v).hex()}
    return v

def error(e):
    return {'type':type(e).__name__,'code':e.args[0] if e.args else None,
            'sqlstate':getattr(e,'sqlstate',None),'message':str(e),
            'traceback':traceback.format_exc()}

def save(name,value):
    path=P/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(norm(value),indent=2,ensure_ascii=False)+'\n')

def record(project,engine,workflow,fn,phase='native'):
    start=time.monotonic()
    r={'project':project,'engine':engine,'workflow':workflow,'phase':phase}
    try:r.update(status='pass',details=norm(fn()))
    except Exception as e:r.update(status='error',error=error(e))
    r['seconds']=round(time.monotonic()-start,3)
    with (P/'workflow-results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(project,engine,phase,workflow,r['status'],flush=True)
    return r

def geom_constructor(engine,srid=4326):
    return f"ST_GeomFromText(%s,{srid},'axis-order=long-lat')" if engine=='mysql' and srid else f'ST_GeomFromText(%s,{srid})'
