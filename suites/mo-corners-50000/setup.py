import sys,json,hashlib,time
from pathlib import Path
sys.path.insert(0,'/workspace/mo-cases-50000');import runner as b
P=Path('/workspace/mo-corners-50000');E=Path('/workspace/mo-enterprise-50000')
c=b.connect('mo',db=None,timeout=60);log=[]
def q(sql,params=None):
 try:r=b.norm(b.query(c,sql,params));log.append({'sql':sql,'rows':r});return r
 except Exception as e:log.append({'sql':sql,'error':str(e)});raise
q('create database if not exists corners50');q('use corners50')
q('create table if not exists fixtures(id int primary key,grp int,v bigint,label text,j json)')
if not q('select count(*) from fixtures')[0][0]:
 with c.cursor() as cur:cur.executemany('insert into fixtures values(%s,%s,%s,%s,%s)',[(i,i%7,i*13-700,'alpha' if i%2==0 else '中文😀',json.dumps({'id':i,'v':i*13-700})) for i in range(200)])
q('create or replace view cv_read as select id,v from fixtures')
for role in ['corner_readrole','corner_writerole','corner_emptyrole']:
 q(f'create role if not exists {role}');q(f'grant connect on account * to {role}')
q("create user if not exists corner_reader identified by '111' default role corner_readrole")
q("create user if not exists corner_writer identified by '111' default role corner_writerole")
q('grant select on table corners50.fixtures to corner_readrole');q('grant select on view corners50.cv_read to corner_readrole')
q('grant select,insert,update,delete on table corners50.* to corner_writerole')
q("create or replace function cu_sqladd(a bigint,b bigint) returns bigint language sql as '$1+$2'")
q("create or replace function cu_nested(a bigint,b bigint) returns bigint language sql as 'cu_sqladd($1,$2)*2'")
q("create or replace function cu_json(a varchar) returns bigint language sql as 'cast(json_extract($1,''$.v'') as bigint)'")
funcs=[
 ('cu_pyadd','a bigint,b bigint','bigint','add',"def add(a,b):\n return None if a is None or b is None else a+b"),
 ('cu_pystr','a text','text','echo',"def echo(a):\n return None if a is None else a+'|中文😀'"),
 ('cu_pyvec','a bigint,b bigint','bigint','vadd',"def vadd(a,b):\n return [None if x is None or y is None else x+y for x,y in zip(a,b)]\nvadd.vector=True"),
 ('cu_pyerr','a bigint','bigint','bad',"def bad(a):\n raise ValueError('MO_CASE_INTENTIONAL_ERROR_'+str(a))"),
 ('cu_pyjson','a json','bigint','jval',"def jval(a):\n import json\n if isinstance(a,str):a=json.loads(a)\n return a['v']"),
 ('cu_pydec','a decimal(18,4)','decimal(18,4)','dval',"def dval(a):\n import decimal\n return a*decimal.Decimal('2')"),
]
for name,args,rett,handler,body in funcs:q(f"create or replace function {name}({args}) returns {rett} language python as $$\n{body}\n$$ handler '{handler}'")
procs=[
 ('cp_if(in n bigint)',"begin if n<0 then select -n; elseif n=0 then select 0; else select n*2; end if; end"),
 ('cp_sum(in n int)',"begin declare i int default 0; declare s bigint default 0; while i<n do set s=s+i; set i=i+1; end while; select s; end"),
 ('cp_repeat(in n int)',"begin declare i int default 0; repeat set i=i+1; until i>=n end repeat; select i; end"),
 ('cp_loop(in n int)',"begin declare i int default 0; lab: loop set i=i+1; if i>=n then leave lab; end if; end loop lab; select i; end"),
 ('cp_scope(in n int)',"begin declare x int default 1; begin declare x int default 2; set @scope_inner=x+n; end; select @scope_inner,x+n; end"),
 ('cp_io(inout n bigint)',"begin set n=n*3+1; end"),
 ('cp_json(in j varchar)',"begin select cast(json_extract(j,'$.v') as bigint); end"),
]
for sig,body in procs:q(f"create or replace procedure {sig} %s",[body])
q('create table if not exists cp_atomic_sink(id bigint primary key,n bigint)')
q('create table if not exists cp_checkpoint(id int primary key,n bigint)')
q('insert into cp_checkpoint values(1,0) on duplicate key update n=0')
q("create or replace procedure cp_abort(in cid bigint,in val bigint) 'begin insert into cp_atomic_sink values(cid,val); update cp_checkpoint set n=val where id=1; insert into cp_missing values(1); end'")
q("create or replace procedure cp_star(in n bigint,out o bigint) language 'starlark' $$out_o = n*n + 3$$")
q("set sql_mode='PIPES_AS_CONCAT'")
q("create or replace procedure cp_mode(in s varchar) 'begin select s||''|mode''; end'")
q("set sql_mode=''")
q('create table if not exists ct_control(kind int primary key,cid bigint,v bigint,ready int)')
q('create table if not exists ct_sink(kind int,cid bigint primary key,v bigint)')
for k in range(6):q('insert into ct_control values(%s,0,0,0) on duplicate key update cid=0,v=0,ready=0',[k])
tasks=[
 "create task ct_success as begin insert into ct_sink select kind,cid,v from ct_control where kind=0; end",
 "create task ct_gate_false when (exists(select 1 from ct_control where kind=1 and ready=1)) as begin insert into ct_sink select kind,cid,v from ct_control where kind=1; end",
 "create task ct_gate_true when (exists(select 1 from ct_control where kind=2 and ready=1)) as begin insert into ct_sink select kind,cid,v from ct_control where kind=2; end",
 "create task ct_abort as begin call cp_task_abort(); end",
 "create task ct_error as begin insert into ct_missing values(1); end",
 "create task ct_idempotent as begin insert into ct_sink select kind,cid,v from ct_control where kind=5 and not exists(select 1 from ct_sink where cid=ct_control.cid); end",
]
q("create or replace procedure cp_task_abort() 'begin insert into ct_sink select kind,cid,v from ct_control where kind=3; update cp_checkpoint set n=99 where id=1; insert into ct_missing values(1); end'")
for t in tasks:
 name=t.split()[2];q(f'drop task if exists {name}');q(t)
q('create database if not exists enterprise50');q('use enterprise50')
q('create table if not exists tx_rows(id bigint primary key,n bigint,j json,v vecf32(3))')
q('create table if not exists tx_hot(id int primary key,n bigint)')
q('insert into tx_hot values(1,0) on duplicate key update n=0')
q('create table if not exists user_target(id int primary key,n bigint)')
q('insert into user_target values(1,100),(2,200) on duplicate key update n=values(n)')
q('create database if not exists pub50');q('create table if not exists pub50.visible(id bigint primary key,n bigint,label text)')
q('create table if not exists pub50.hidden(id bigint primary key,n bigint)')
q('insert into pub50.visible values(1,13,\'alpha\'),(2,26,\'中文😀\') on duplicate key update n=values(n)')
q('insert into pub50.hidden values(1,999) on duplicate key update n=values(n)')
for account in ['corner_a','corner_b']:
 q(f"create account if not exists {account} admin_name 'admin' identified by '111'")
 tc=b.connect('mo',db=None,timeout=60)
 import pymysql
 tc.close();tc=pymysql.connect(host='127.0.0.1',port=6001,user=account+':admin:accountadmin',password='111',autocommit=True,read_timeout=60,ssl_disabled=True)
 for sql in ['create database if not exists enterprise50','use enterprise50','create table if not exists own(id bigint primary key,n bigint,j json)','create role if not exists readrole','grant connect on account * to readrole',"create user if not exists reader identified by '111' default role readrole",'grant select on table enterprise50.own to readrole']:
  b.query(tc,sql)
 b.query(tc,'insert into own values(%s,%s,%s) on duplicate key update n=values(n)',[1,101 if account=='corner_a' else 202,json.dumps({'tenant':account})]);tc.close()
q('drop publication if exists pub50_allowed');q('create publication pub50_allowed database pub50 table visible account corner_a')
q('drop publication if exists pub50_all');q('create publication pub50_all database pub50 table visible account all')
for account in ['corner_a','corner_b']:
 tc=pymysql.connect(host='127.0.0.1',port=6001,user=account+':admin:accountadmin',password='111',autocommit=True,read_timeout=60,ssl_disabled=True)
 b.query(tc,'create database if not exists sub50 from sys publication pub50_all')
 if account=='corner_a':b.query(tc,'create database if not exists allowed50 from sys publication pub50_allowed')
 tc.close()
profiles={'root':{'user':'root','password':'111','db':'corners50'},'reader':{'user':'sys:corner_reader:corner_readrole','password':'111','db':'corners50'},'writer':{'user':'sys:corner_writer:corner_writerole','password':'111','db':'corners50'},'enterprise_root':{'user':'root','password':'111','db':'enterprise50'}}
for a in ['corner_a','corner_b']:
 profiles[a]={'user':a+':admin:accountadmin','password':'111','db':'enterprise50'}
 profiles[a+'_reader']={'user':a+':reader:readrole','password':'111','db':'enterprise50'}
for p in [P,E]:(p/'profiles.json').write_text(json.dumps(profiles,indent=2));(p/'setup-log.json').write_text(json.dumps(log,indent=2,ensure_ascii=False))
c.close();print('Fixtures ready')
