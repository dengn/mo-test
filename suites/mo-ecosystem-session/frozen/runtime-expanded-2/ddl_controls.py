from common import *
N='rt2_sql';out={'runtime_ref':REF,'mysql_version':sql(13306,None,'SELECT VERSION()'),'mode':{},'cases':[]}
for p in [13306,6001]:
 sql(p,None,'CREATE DATABASE '+N);out['mode'][str(p)]=sql(p,None,'SELECT @@sql_mode,@@time_zone')
cases={'rename':("ALTER TABLE t_rename RENAME COLUMN v TO renamed_v","UPDATE t_rename SET renamed_v='renamed' WHERE id=1"),'drop':('ALTER TABLE t_drop DROP COLUMN dropped',"UPDATE t_drop SET v='dropped' WHERE id=1"),'widen':('ALTER TABLE t_widen MODIFY COLUMN n BIGINT','UPDATE t_widen SET n=2147483648 WHERE id=1'),'nullability':("ALTER TABLE t_nullability MODIFY COLUMN nullable VARCHAR(10) NOT NULL DEFAULT 'fill'","INSERT INTO t_nullability(id,v,n) VALUES(2,'new',2)"),'default':("ALTER TABLE t_default ALTER COLUMN v SET DEFAULT 'def'",'INSERT INTO t_default(id,n) VALUES(2,2)'),'overflow':(None,'UPDATE t_overflow SET n=2147483648 WHERE id=1')}
for name,(ddl,dml) in cases.items():
 case={'name':name,'ddl':ddl,'dml':dml,'databases':{}}
 for p in [13306,6001]:
  table='t_'+name;sql(p,N,'CREATE TABLE '+table+'(id INT PRIMARY KEY,v VARCHAR(10),n SMALLINT,nullable VARCHAR(10),dropped VARCHAR(10))');sql(p,N,'INSERT INTO '+table+" VALUES(1,'short',30000,'fill','old')")
  r={}
  for phase,stmt in [('ddl',ddl),('dml',dml)]:
   if stmt:
    try:r[phase]={'success':True,'rows':sql(p,N,stmt)}
    except Exception as e:r[phase]={'success':False,'error':str(e)}
  r['rows']=sql(p,N,'SELECT * FROM '+table+' ORDER BY id');r['schema']=sql(p,N,'SHOW COLUMNS FROM '+table);case['databases'][str(p)]=r
 case['values_equal']=case['databases']['13306']['rows']==case['databases']['6001']['rows'];out['cases'].append(case);dump(B/'ddl-native-controls.json',out);print(name,'same_values',case['values_equal'],'MO',case['databases']['6001'].get('ddl'),case['databases']['6001'].get('dml'),flush=True)
