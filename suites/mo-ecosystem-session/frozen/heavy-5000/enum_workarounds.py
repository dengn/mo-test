from runtime import *
out=[]
for kind,ddl,new in [('enum',"ENUM('','red','中文😀')",'中文😀'),('set',"SET('a','文')",'文')]:
 t='repro_'+kind+'_target';s='repro_'+kind+'_stage'
 for name,q,params in [('single_table_bound',f'UPDATE {t} SET v=%s WHERE id=1',(new,)),('join_explicit_cast',f'UPDATE {t} AS target JOIN {s} AS incoming ON target.id=incoming.id SET target.v=CAST(incoming.v AS CHAR)',None),('rename_incoming_column',f'UPDATE {t} AS target JOIN (SELECT id,v AS incoming_value FROM {s}) AS incoming ON target.id=incoming.id SET target.v=incoming.incoming_value',None)]:
  r={'kind':kind,'name':name,'sql':q}
  try:sql(q,params);r.update(status='passed',rows=sql('SELECT id,CAST(v AS CHAR) FROM '+t+' ORDER BY id'))
  except Exception as e:r.update(status='failed',error=str(e))
  out.append(r)
dump(B/'enum-set-workaround-controls.json',out);print(out)
