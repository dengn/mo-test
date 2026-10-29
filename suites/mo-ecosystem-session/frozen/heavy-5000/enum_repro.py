from runtime import *
out=[]
for kind,ddl in [('enum',"ENUM('','red','中文😀')"),('set',"SET('a','文')"),('varchar','VARCHAR(100)')]:
 for port in [6001,13306]:
  for n in range(3):
   t='repro_'+kind+'_target';s='repro_'+kind+'_stage';initial='red' if kind=='enum' else 'a';new='中文😀' if kind=='enum' else '文';row={'kind':kind,'port':port,'repeat':n}
   for table in [t,s]:sql('DROP TABLE IF EXISTS '+table,port=port);sql('CREATE TABLE '+table+'(id BIGINT PRIMARY KEY,v '+ddl+')',port=port)
   sql('INSERT INTO '+t+' VALUES(1,%s),(2,NULL)',(initial,),port=port);sql('INSERT INTO '+s+' VALUES(1,%s)',(new,),port=port)
   q=f'UPDATE {t} AS target JOIN {s} AS incoming ON target.id=incoming.id SET target.v=incoming.v';row['sql']=q
   try:sql(q,port=port);row.update(status='completed',rows=sql('SELECT id,CAST(v AS CHAR) FROM '+t+' ORDER BY id',port=port))
   except Exception as e:row.update(status='failed',error=str(e),rows=sql('SELECT id,CAST(v AS CHAR) FROM '+t+' ORDER BY id',port=port))
   out.append(row)
dump(B/'enum-set-update-join-repro.json',out);print([(r['kind'],r['port'],r['status'],r.get('error')) for r in out],flush=True)
