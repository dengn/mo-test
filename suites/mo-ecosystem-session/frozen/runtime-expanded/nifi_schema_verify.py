import json,time,pymysql
from pathlib import Path
B=Path(__file__).parent;out=json.loads((B/'nifi-runtime-result.json').read_text())
def db(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='runtime_ecosystem',autocommit=True)
def save():(B/'nifi-runtime-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
with db(13306) as d,d.cursor() as c:
 c.execute('ALTER TABLE nifi_source ADD COLUMN added_tag VARCHAR(100) NULL')
 c.execute("UPDATE nifi_source SET added_tag='NiFi模式变化 中文',updated=24 WHERE id=1")
with db(6001) as d,d.cursor() as c:
 c.execute('SHOW COLUMNS FROM nifi_outbox_target');has_column=any(r[0]=='added_tag' for r in c.fetchall())
out['cases'].append({'name':'new-source-column-unadapted-profile-gap','status':'expected_gap','target_has_new_column':has_column,'note':'Versioned SQL outbox does not automatically transport a new field; explicit schema/profile adaptation required. This is not generic automatic schema evolution.'});save()
cols=['id','s','u','d','payload','name','ts','doc','updated','added_tag']
def expr(prefix):
 args=[]
 for col in cols:
  x=prefix+'.'+col
  part=f"IF({x} IS NULL,'NULL',CONCAT(\"X'\",HEX({x}),\"'\"))" if col=='payload' else f"IF({x} IS NULL,'NULL',QUOTE(CAST({x} AS CHAR)))"
  if args:args.append("','")
  args.append(part)
 head="'INSERT INTO nifi_outbox_target("+','.join(cols)+") VALUES('"
 tail="') ON DUPLICATE KEY UPDATE "+','.join(x+'=VALUES('+x+')' for x in cols if x!='id')+"'"
 return 'CONCAT('+','.join([head]+args+[tail])+')'
with db(6001) as d,d.cursor() as c:c.execute('ALTER TABLE nifi_outbox_target ADD COLUMN added_tag VARCHAR(100) NULL')
with db(13306) as d,d.cursor() as c:
 for op in ['INSERT','UPDATE']:
  c.execute('DROP TRIGGER nifi_'+op.lower())
  c.execute(f'CREATE TRIGGER nifi_{op.lower()} AFTER {op} ON nifi_source FOR EACH ROW INSERT INTO nifi_outbox(sqltext) VALUES({expr("NEW")})')
 c.execute('INSERT INTO nifi_outbox(sqltext) SELECT '+expr('src')+' FROM nifi_source src ORDER BY id')
start=time.monotonic();expected=None;actual=None
while time.monotonic()-start<45:
 with db(13306) as d,d.cursor() as c:c.execute('SELECT id,added_tag FROM nifi_source ORDER BY id');expected=c.fetchall()
 with db(6001) as d,d.cursor() as c:c.execute('SELECT id,added_tag FROM nifi_outbox_target ORDER BY id');actual=c.fetchall()
 if expected==actual:break
 time.sleep(1)
out['cases'].append({'name':'new-column-after-explicit-target-and-profile-adaptation','status':'passed' if actual==expected else 'failed','source':expected,'sink':actual});save();print(out['cases'][-1],flush=True)
