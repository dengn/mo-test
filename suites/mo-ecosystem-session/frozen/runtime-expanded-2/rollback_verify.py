from common import *
out={'runtime_ref':REF,'cases':[]}
for database,table,sink,port in [('runtime_ecosystem','nifi_source','nifi_outbox_target',6001),('rt2_kafka','wide','wide',6001)]:
 before=sql(13306,database,'SELECT id,name,updated FROM '+table+' ORDER BY id');outbox_before=sql(13306,database,'SELECT MAX(seq) FROM nifi_outbox')[0][0] if table=='nifi_source' else None
 with db(13306,database) as d,d.cursor() as c:
  d.autocommit(False);c.execute('INSERT INTO '+table+"(id,name,updated) VALUES(8000,'回滚新增',8000)");c.execute('UPDATE '+table+" SET name='回滚更新',updated=8001 WHERE id=1" if table=='nifi_source' else 'UPDATE '+table+" SET name='回滚更新',updated=8001 WHERE id=3");c.execute('DELETE FROM '+table+' WHERE id=4' if table=='nifi_source' else 'DELETE FROM '+table+' WHERE id=7');d.rollback()
 after=sql(13306,database,'SELECT id,name,updated FROM '+table+' ORDER BY id');outbox_after=sql(13306,database,'SELECT MAX(seq) FROM nifi_outbox')[0][0] if table=='nifi_source' else None
 time.sleep(4);target=sql(port,database,'SELECT id,name,updated FROM '+sink+' ORDER BY id')
 case={'name':table+'-source-transaction-rollback','status':'passed' if before==after==target and outbox_before==outbox_after else 'failed','source_before':before,'source_after':after,'target_after':target,'outbox_max_seq_before':outbox_before,'outbox_max_seq_after':outbox_after};out['cases'].append(case);dump(B/'source-rollback-result.json',out);print(case['name'],case['status'],flush=True)
