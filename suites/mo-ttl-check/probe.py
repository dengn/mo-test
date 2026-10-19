"""Reproducible TTL capability probe; only creates/changes its own database."""
import datetime
import json
import os
from pathlib import Path
import time
import pymysql

P=Path(__file__).resolve().parent
DB='mo_ttl_capability_20261013'
conn=pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6013')),
    user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),autocommit=True,
    charset='utf8mb4',connect_timeout=5,read_timeout=30)
records=[]
def sql(s):
    t=time.monotonic()
    try:
        with conn.cursor() as cur:
            cur.execute(s)
            result=cur.fetchall() if cur.description else []
            r={'sql':s,'status':'ok','rows':result,'affected_rows':cur.rowcount}
    except Exception as e:r={'sql':s,'status':'error','error':str(e),'error_code':e.args[0]}
    r['seconds']=round(time.monotonic()-t,3);records.append(r)
    P.joinpath('runtime-results.json').write_text(json.dumps(records,indent=2,default=str)+'\n')
    print(json.dumps(r,default=str),flush=True)
    return r
def require(s):
    r=sql(s)
    assert r['status']=='ok',r
    return r['rows']
def ids(table='events'):
    return [r[0] for r in require('select id from '+table+' order by id')]

require('select version(),git_version(),now(),@@time_zone')
require('create database if not exists '+DB)
require('use '+DB)
require("set time_zone='+00:00'")
require('drop task if exists ttl_cleanup_probe')
for name in ['native_ttl','properties_ttl','events']:
    require('drop table if exists '+name)
for statement in [
    "create table native_ttl(id int,expires_at datetime) TTL=expires_at",
    "create table native_ttl(id int,expires_at datetime) TTL = expires_at + INTERVAL 1 DAY",
    "create table native_ttl(id int,expires_at datetime) TTL = 'expires_at + INTERVAL 1 DAY'",
    "create table native_ttl(id int,expires_at datetime) TTL_ENABLE='ON'",
    "create table native_ttl(id int,expires_at datetime) WITH (ttl='1d')",
    "create event ttl_mysql_event on schedule every 1 second do select 1",
]:
    r=sql(statement)
    if r['status']=='ok':require('drop table if exists native_ttl')
# Generic PROPERTIES can accept arbitrary metadata. Acceptance alone does not
# imply a policy exists, so probe both metadata and actual expired-row behavior.
r=sql("create table properties_ttl(id int,expires_at datetime) properties('ttl'='expires_at','ttl_enable'='true')")
if r['status']=='ok':
    require("insert into properties_ttl values (1,date_sub(now(),interval 1 day))")
    sql('show create table properties_ttl')
require('create table events(id int primary key,expires_at datetime null,kind varchar(32),index idx_expiry(expires_at))')
require("insert into events values (1,date_sub(now(),interval 1 day),'already-expired'),(2,date_add(now(),interval 1 day),'future'),(3,null,'no-expiration'),(4,date_add(now(),interval 12 second),'expires-soon')")
assert ids()==[1,2,3,4]
require("create task ttl_cleanup_probe schedule '*/2 * * * * *' timezone 'UTC' as begin delete from events where expires_at <= now(); end")
deadline=time.monotonic()+45
observed={}
while time.monotonic()<deadline:
    observed['ids']=ids()
    if observed['ids']==[2,3]:break
    time.sleep(1)
observed['scheduled_cleanup_verified']=observed['ids']==[2,3]
sql('show task runs for ttl_cleanup_probe limit 8')
require('alter task ttl_cleanup_probe suspend')
require("insert into events values (5,date_sub(now(),interval 1 day),'suspended')")
time.sleep(4)
observed['suspended_expired_row_retained']=5 in ids()
require('execute task ttl_cleanup_probe')
observed['manual_cleanup_verified']=ids()==[2,3]
if r['status']=='ok':observed['arbitrary_ttl_properties_did_not_expire_row']=ids('properties_ttl')==[1]
require('drop task ttl_cleanup_probe')
sql('select count(*) from events')
sql('select git_version(),1')
P.joinpath('assertions.json').write_text(json.dumps(observed,indent=2)+'\n')
conn.close()
assert observed['scheduled_cleanup_verified'],observed
assert observed['suspended_expired_row_retained'],observed
assert observed['manual_cleanup_verified'],observed
if r['status']=='ok':assert observed['arbitrary_ttl_properties_did_not_expire_row'],observed
