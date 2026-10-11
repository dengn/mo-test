import json,hashlib,collections
from pathlib import Path
P=Path('/workspace/mo-enterprise-50000');cases=[];profiles=json.loads((P/'profiles.json').read_text());AUTH='privilege|permission|access denied|authorized|role'
def st(sql,params=None,expected=None,**kw):
 s={'sql':sql,'params':params or [],**kw}
 if expected is not None:s['expected']=expected
 return s
def auth(actor,**kw):return {'authenticate':True,'actor':actor,**kw}
def add(mod,family,steps,cleanup=None,**kw):
 n=len(cases)+1;c={'id':f'M{n:06d}','module':mod,'family':mod+'.'+family,'steps':steps,'cleanup':cleanup or [],**kw};c['operation_sha256']=hashlib.sha256(json.dumps({k:v for k,v in c.items() if k not in ['id','operation_sha256']},sort_keys=True,ensure_ascii=False).encode()).hexdigest();cases.append(c)
for i in range(5000):
 k=i%5;u=f'mu{i}';r=f'mr{i}';z=f'mz{i}';u2=f'mv{i}';actor=u
 profiles[actor]={'user':f'sys:{u}:{r}','password':'111','db':'enterprise50'}
 steps=[st(f'create role {r}'),st(f'grant connect on account * to {r}'),st(f"create user {u} identified by '111' default role {r}")]
 cleanup=[st(f'drop user if exists {u}'),st(f'drop user if exists {u2}'),st(f'drop role if exists {z}'),st(f'drop role if exists {r}')]
 if k==0:
  f='password_rotation';steps += [auth(actor),st(f"alter user {u} identified by 'new{i}'"),auth(actor,reject=True,password='111'),auth(actor,password=f'new{i}')]
 elif k==1:
  f='role_cycle';steps += [st(f'create role {z}'),st(f'grant {r} to {z}'),st(f'grant {z} to {r}',reject=True,error_pattern='cycle|loop|inherit|invalid|cannot grant role')]
 elif k==2:
  f='revoke_existing_session';steps += [st(f'grant select on table enterprise50.user_target to {r}'),st('select n from user_target where id=1',expected=[[100]],actor=actor),st(f'revoke select on table enterprise50.user_target from {r}'),st('select n from user_target where id=1',reject=True,error_pattern=AUTH,actor=actor)]
 elif k==3:
  f='grant_option_delegate';profiles[u2]={'user':f'sys:{u2}:{z}','password':'111','db':'enterprise50'}
  steps += [st(f'create role {z}'),st(f'grant connect on account * to {z}'),st(f"create user {u2} identified by '111' default role {z}"),st(f'grant select on table enterprise50.user_target to {r} with grant option'),st(f'grant select on table enterprise50.user_target to {z}',actor=actor),st('select n from user_target order by id',expected=[[100],[200]],actor=u2)]
 else:
  f='active_role_switch';steps += [st(f'create role {z}'),st(f'grant {z} to {u}'),st(f'grant select on table enterprise50.user_target to {z}'),st('select n from user_target where id=1',reject=True,error_pattern=AUTH,actor=actor),st(f'set role {z}',actor=actor),st('select n from user_target where id=1',expected=[[100]],actor=actor)]
 add('users_roles',f,steps,cleanup,actor='enterprise_root')
profiles['spoof_a']={'user':'corner_a:reader:accountadmin','password':'111','db':'enterprise50'}
profiles['spoof_b']={'user':'corner_b:reader:moadmin','password':'111','db':'enterprise50'}
for i in range(10000):
 k=i%10;cid=5001+i;v=i*31+17
 if k in [0,1]:
  who='corner_a' if k==0 else 'corner_b';f='account_local_identity_'+who
  steps=[st('select n,json_unquote(json_extract(j,\'$.tenant\')) from own where id=1',expected=[[101 if k==0 else 202,who]])];actor=who
 elif k in [2,3]:
  who='corner_a' if k==2 else 'corner_b';f='same_pk_distinct_tenants_'+who;actor=who;other='corner_b' if k==2 else 'corner_a'
  steps=[st('insert into own values(%s,%s,%s)',[cid,v,json.dumps({'cid':cid,'tenant':who})]),st('select n from own where id=%s',[cid],[[v]]),st('select count(*) from own where id=%s',[cid],[[0]],actor=other)]
 elif k==4:
  f='reader_no_write';actor='corner_a_reader';steps=[st('insert into own values(%s,%s,\'{}\')',[cid,v],reject=True,error_pattern=AUTH)]
 elif k==5:
  f='reader_no_role_admin';actor='corner_b_reader';steps=[st(f'create role deny_m{cid}',reject=True,error_pattern=AUTH)]
 elif k==6:
  f='tenant_system_users_hidden';actor='corner_a';steps=[st("select count(*) from mo_catalog.mo_user where user_name='root'",expected=[[0]])]
 elif k==7:
  f='cannot_claim_accountadmin';actor='corner_a';steps=[auth('spoof_a',reject=True,error_pattern='role|grant|permission|password')]
 elif k==8:
  f='cannot_claim_system_moadmin';actor='corner_b';steps=[auth('spoof_b',reject=True,error_pattern='role|grant|permission|password')]
 else:
  f='rollback_not_visible_in_other_tenant';actor='corner_a';steps=[st('start transaction'),st('insert into own values(%s,%s,\'{}\')',[cid,v]),st('select count(*) from own where id=%s',[cid],[[0]],actor='corner_b'),st('rollback'),st('select count(*) from own where id=%s',[cid],[[0]])]
 add('multitenant',f,steps,actor=actor)
for i in range(15000):
 k=i%15;cid=15001+i;v=i*101-700000;row=[cid,v,json.dumps({'v':v}),json.dumps([i%17,2,3])]
 ins=st('insert into tx_rows values(%s,%s,%s,%s)',row,session='a')
 read=st('select n from tx_rows where id=%s',[cid],[[v]],session='a')
 cleanup=[st('delete from tx_rows where id=%s',[cid],actor='enterprise_root')]
 if k==0:
  f='commit_visibility';steps=[st('start transaction',session='a'),ins,st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b'),st('commit',session='a'),st('select n from tx_rows where id=%s',[cid],[[v]],session='b')]
 elif k==1:
  f='rollback_visibility';steps=[st('start transaction',session='a'),ins,read,st('rollback',session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b')]
 elif k==2:
  f='dirty_read_forbidden';steps=[st('start transaction',session='a'),ins,st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b'),st('rollback',session='a')]
 elif k==3:
  f='read_committed_refresh';steps=[ins,st('start transaction',session='b'),st('select n from tx_rows where id=%s',[cid],[[v]],session='b'),st('update tx_rows set n=n+1 where id=%s',[cid],session='a'),st('select n from tx_rows where id=%s',[cid],[[v+1]],session='b'),st('commit',session='b'),st('select n from tx_rows where id=%s',[cid],[[v+1]],session='b')]
 elif k==4:
  f='read_own_mixed_update';steps=[ins,st('start transaction',session='a'),st('update tx_rows set n=n+3,j=json_object(\'v\',n+3) where id=%s',[cid],session='a'),st('select n from tx_rows where id=%s',[cid],[[v+3]],session='a'),st('rollback',session='a'),read]
 elif k==5:
  f='delete_rollback';steps=[ins,st('start transaction',session='a'),st('delete from tx_rows where id=%s',[cid],session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='a'),st('rollback',session='a'),read]
 elif k==6:
  f='delete_commit';steps=[ins,st('start transaction',session='a'),st('delete from tx_rows where id=%s',[cid],session='a'),st('commit',session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b')]
 elif k==7:
  f='duplicate_then_rollback';dup={**ins,'reject':True,'error_pattern':'Duplicate|duplicate|1062'};steps=[st('start transaction',session='a'),ins,dup,st('rollback',session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b')]
 elif k==8:
  f='autocommit_off';steps=[st('set autocommit=0',session='a'),ins,read,st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b'),st('commit',session='a'),st('select n from tx_rows where id=%s',[cid],[[v]],session='b')]
 elif k==9:
  f='null_json_vector_commit';steps=[st('start transaction',session='a'),st('insert into tx_rows values(%s,null,%s,%s)',[cid,json.dumps({'null':None,'text':'中文😀'}),'[1,2,3]'],session='a'),st('commit',session='a'),st('select n,l2_distance(v,\'[1,2,3]\') from tx_rows where id=%s',[cid],[[None,0]],session='b')]
 elif k==10:
  f='read_only_snapshot';steps=[st('start transaction',session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='a'),st('commit',session='a')]
 elif k==11:
  f='update_rollback';steps=[ins,st('start transaction',session='a'),st('update tx_rows set n=%s where id=%s',[-v,cid],session='a'),st('rollback',session='a'),read]
 elif k==12:
  f='delete_insert_replacement';steps=[ins,st('start transaction',session='a'),st('delete from tx_rows where id=%s',[cid],session='a'),st('insert into tx_rows values(%s,%s,\'{}\',\'[4,5,6]\')',[cid,v+9],session='a'),st('commit',session='a'),st('select n from tx_rows where id=%s',[cid],[[v+9]],session='b')]
 elif k==13:
  f='savepoint_boundary';steps=[st('start transaction',session='a'),ins,st(f'savepoint s{cid}',session='a',boundary=True),st('rollback',session='a'),st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b')]
 else:
  f='disconnect_rollback';steps=[st('start transaction',session='a'),ins,read,{'disconnect':'a'},st('select count(*) from tx_rows where id=%s',[cid],[[0]],session='b'),st('insert into tx_rows values(%s,%s,\'{}\',\'[1,2,3]\')',[cid,v+1],session='b'),st('select n from tx_rows where id=%s',[cid],[[v+1]],session='b')]
 add('transactions',f,steps,cleanup,actor='enterprise_root')
for i in range(10000):
 k=i%10;cid=30001+i;v=i*17;actor='corner_a';cleanup=[]
 if k==0:f='subscribed_projection';steps=[st('select id,n from sub50.visible where id<=2 order by id',expected=[[1,13],[2,26]])]
 elif k==1:f='unpublished_table_hidden';steps=[st('select * from sub50.hidden where id=%s',[cid],reject=True,error_pattern='no such table|not.*publication|not.*published|does not exist|not found')]
 elif k==2:f='subscription_readonly_insert';steps=[st('insert into sub50.visible values(%s,%s,\'denied\')',[cid,v],reject=True,error_pattern='subscription|publication|public table|read.only|privilege')]
 elif k==3:f='subscription_readonly_update';steps=[st('update sub50.visible set n=0 where id=%s',[-cid],reject=True,error_pattern='subscription|publication|public table|read.only|privilege')]
 elif k==4:f='unauthorized_subscription';actor='corner_b';steps=[st(f'create database denied_sub{cid} from sys publication pub50_allowed',reject=True,error_pattern='account|publication|privilege|authorized')]
 elif k==5:f='allowed_account_query';steps=[st('select id,n from allowed50.visible where id=1',expected=[[1,13]])]
 elif k==6:f='incremental_publisher_visibility';steps=[st('insert into pub50.visible values(%s,%s,%s)',[cid,v,'pub_'+str(i)],actor='enterprise_root'),st('select n,label from sub50.visible where id=%s',[cid],[[v,'pub_'+str(i)]])];cleanup=[st('delete from pub50.visible where id=%s',[cid],actor='enterprise_root')]
 elif k==7:f='local_join_subscription';steps=[st('select a.n,b.n from own a join sub50.visible b on a.id=b.id where a.id=1',expected=[[101,13]])]
 elif k==8:f='subscription_cte_window';steps=[st('with a as(select id,n from sub50.visible where id<=2) select id,n,sum(n) over(order by id) from a order by id',expected=[[1,13,'13'],[2,26,'39']])]
 else:f='subscriber_b_view';actor='corner_b';steps=[st('select id,n from sub50.visible where id<=2 order by id',expected=[[1,13],[2,26]])]
 add('pubsub',f,steps,cleanup,actor=actor)
for i in range(10000):
 k=i%10;n=i*101+7;t=f'gb{i}';s=f'gs{i}';steps=[st(f'create table {t}(id int primary key,u bigint unique,n bigint,j json,v vecf32(3))'),st(f'insert into {t} values(1,1,%s,%s,\'[1,2,3]\'),(2,2,%s,%s,\'[4,5,6]\'),(3,3,%s,%s,\'[7,8,9]\')',[n,json.dumps({'n':n}),n+1,json.dumps({'n':n+1}),n+2,json.dumps({'n':n+2})]),st(f'data branch create table {s} from {t}')]
 cleanup=[st(f'drop table if exists {s}',actor='enterprise_root'),st(f'drop table if exists {t}',actor='enterprise_root')]
 exp=[[1,n],[2,n+1],[3,n+2]]
 if k==0:
  f='copy_isolation';steps += [st(f'update {s} set n=n+10 where id=1'),st(f'select id,n from {t} order by id',expected=exp),st(f'select n from {s} where id=1',expected=[[n+10]])]
 elif k==1:
  f='merge_disjoint_insert';steps += [st(f'insert into {s} values(4,4,%s,\'{{}}\',\'[1,2,3]\')',[n+4]),st(f'insert into {t} values(5,5,%s,\'{{}}\',\'[1,2,3]\')',[n+5]),st(f'data branch merge {s} into {t}'),st(f'select id,n from {t} order by id',expected=exp+[[4,n+4],[5,n+5]])]
 elif k==2:
  f='merge_update';steps += [st(f'update {s} set n=n+10 where id=1'),st(f'data branch merge {s} into {t}'),st(f'select id,n from {t} order by id',expected=[[1,n+10]]+exp[1:])]
 elif k==3:
  f='merge_delete';steps += [st(f'delete from {s} where id=2'),st(f'data branch merge {s} into {t}'),st(f'select id,n from {t} order by id',expected=[exp[0],exp[2]])]
 elif k in [4,5,6]:
  f=['conflict_error','conflict_skip','conflict_accept'][k-4];steps += [st(f'update {t} set n=n+10 where id=1'),st(f'update {s} set n=n+20 where id=1')]
  if k==4:steps += [st(f'data branch merge {s} into {t}',reject=True,error_pattern='conflict')]
  else:steps += [st(f'data branch merge {s} into {t} when conflict '+('skip' if k==5 else 'accept'))]
  steps += [st(f'select id,n from {t} order by id',expected=[[1,n+(20 if k==6 else 10)]]+exp[1:])]
 elif k==7:
  f='pick_subset';steps += [st(f'update {s} set n=n+20 where id in(1,2)'),st(f'insert into {s} values(4,4,%s,\'{{}}\',\'[1,2,3]\')',[n+4]),st(f'data branch pick {s} into {t} keys(1,4) when conflict accept'),st(f'select id,n from {t} order by id',expected=[[1,n+20]]+exp[1:]+[[4,n+4]])]
 elif k==8:
  f='unique_merge_rejection';steps += [st(f'insert into {s} values(4,4,%s,\'{{}}\',\'[1,2,3]\')',[n+4]),st(f'insert into {t} values(5,4,%s,\'{{}}\',\'[1,2,3]\')',[n+5]),st(f'data branch merge {s} into {t} when conflict accept',reject=True,error_pattern='Duplicate|duplicate'),st(f'select id,n from {t} order by id',expected=exp+[[5,n+5]])]
 else:
  f='schema_type_mismatch';steps += [st(f'alter table {s} add column c varchar(20) default \'x\''),st(f'alter table {t} add column c int default 0'),st(f'data branch diff {s} against {t}',reject=True,error_pattern='schema|different types|compatibility')]
 add('git4data',f,steps,cleanup,actor='enterprise_root')
assert len(cases)==50000
(P/'profiles.json').write_text(json.dumps(profiles,indent=2))
with (P/'cases.jsonl').open('w') as f:
 for c in cases:f.write(json.dumps(c,ensure_ascii=False)+'\n')
coverage={'total':len(cases),'modules':dict(collections.Counter(c['module'] for c in cases)),'families':dict(collections.Counter(c['family'] for c in cases)),'unique_operations':len({c['operation_sha256'] for c in cases})}
(P/'coverage.json').write_text(json.dumps(coverage,indent=2,ensure_ascii=False));print(json.dumps(coverage,ensure_ascii=False))
