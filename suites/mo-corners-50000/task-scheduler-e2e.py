import sys,json,time,concurrent.futures
from pathlib import Path
sys.path.insert(0,'/workspace/mo-corners-50000');import common
P=Path('/workspace/mo-corners-50000');common.profiles=json.loads((P/'profiles.json').read_text());c=common.connect();checks=[]
def q(sql,params=None,reject=False,expect=None):
 t=time.monotonic()
 try:
  r=common.base.norm(common.query(c,{'sql':sql,'params':params or []}));ok=not reject and (expect is None or common.base.equal(r,expect,1e-6));out={'sql':sql,'rows':r,'status':'pass' if ok else 'candidate','expected':expect}
 except Exception as e:out={'sql':sql,'error':common.error(e),'status':'pass_expected_rejection' if reject else 'execution_error'}
 out['seconds']=time.monotonic()-t;checks.append(out);print(json.dumps(out,ensure_ascii=False),flush=True);return out
q('create table e2e_ticks(n bigint,ts timestamp default current_timestamp)')
q('create table e2e_task_sink(id int primary key)')
q("create task e2e_cron schedule '*/2 * * * * *' timezone 'UTC' as begin insert into e2e_ticks(n) values(1); end")
q('alter task e2e_cron resume')
start=time.monotonic();count=0
while time.monotonic()-start<15:
 r=q('select count(*) from e2e_ticks');count=r.get('rows',[[0]])[0][0]
 if count>=2:break
 time.sleep(.5)
checks.append({'scenario':'cron actually scheduled','status':'pass' if count>=2 else 'candidate_scheduler_not_running','ticks':count})
q('alter task e2e_cron suspend');time.sleep(2.5);baseline=q('select count(*) from e2e_ticks').get('rows')
time.sleep(3);q('select count(*) from e2e_ticks',expect=baseline)
q('alter task e2e_cron resume');time.sleep(3);after=q('select count(*) from e2e_ticks').get('rows')
checks.append({'scenario':'resume produced new ticks','status':'pass' if after and baseline and after[0][0]>baseline[0][0] else 'candidate'})
q('alter task e2e_cron suspend')
q("create task e2e_timeout timeout '100ms' as begin insert into e2e_task_sink select sleep(2); end")
q('execute task e2e_timeout',reject=True);q('select count(*) from e2e_task_sink',expect=[[0]])
q("select status from mo_task.sql_task_run where task_name='e2e_timeout' order by run_id desc limit 1",expect=[['FAILED']])
q("create task e2e_retry retry 1 as begin insert into e2e_task_sink values(7); insert into e2e_missing_table values(1); end")
q('execute task e2e_retry',reject=True);q('select * from e2e_task_sink',expect=[[7]])
q("select count(*) from mo_task.sql_task_run where task_name='e2e_retry' and status='FAILED'",expect=[[2]])
q("create task e2e_badzone schedule '*/2 * * * * *' timezone 'No/Such_Zone' as begin select 1; end",reject=True)
q("create task e2e_badcron schedule 'invalid cron expression' as begin select 1; end",reject=True)
for task in ['e2e_cron','e2e_timeout','e2e_retry','e2e_badzone','e2e_badcron']:q('drop task if exists '+task)
q('drop table e2e_ticks');q('drop table e2e_task_sink');c.close()
(P/'task-scheduler-e2e.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False))
