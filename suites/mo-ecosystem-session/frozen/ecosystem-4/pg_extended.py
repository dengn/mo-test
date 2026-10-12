from runtime import *
out={'runtime_ref':REF,'scope':'PostgreSQL extended types through Debezium/JDBC; MO vs independent MySQL target; classify fidelity independently from delivery','cases':[]}
specs=[('temporal',"id BIGINT PRIMARY KEY,clock TIME(6),zoned TIMESTAMPTZ(6),flag BOOLEAN,day DATE","id BIGINT PRIMARY KEY,clock TIME(6),zoned DATETIME(6),flag BOOLEAN,day DATE",[(1,'12:34:56.123456','2026-10-11 12:34:56.123456+05:45',True,'2000-02-29'),(2,'00:00:00.000001','2026-10-11 00:00:00.000001-03:30',False,'9999-12-31'),(3,None,None,None,None)]),
 ('varnum','id BIGINT PRIMARY KEY,n NUMERIC','id BIGINT PRIMARY KEY,n DECIMAL(38,18)',[(1,'123.456789012345678901'),(2,'-0.000000000000000001'),(3,None)]),
 ('arrays','id BIGINT PRIMARY KEY,arr INTEGER[]','id BIGINT PRIMARY KEY,arr JSON',[(1,[1,None,2147483647]),(2,[]),(3,None)])]
for name,src,dst,rows in specs:
 psql('CREATE TABLE eco4_'+name+'('+src+')')
 for row in rows:psql('INSERT INTO eco4_'+name+' VALUES('+','.join(['%s']*len(row))+')',row)
 for port in [6001,13306]:sql(port,'eco4','CREATE TABLE pg_'+name+'('+dst+')')
source=json.loads((B/'pg-source-config.json').read_text());source.update({'topic.prefix':'eco4pgx','slot.name':'eco4_slotx','publication.name':'eco4_publicationx','table.include.list':','.join('public.eco4_'+n for n,_,_,_ in specs)});api('PUT','/connectors/eco4-pgx-source/config',source);dump(B/'pgx-source-config.json',source)
for name,_,_,_ in specs:
 for port in [13306,6001]:
  config=json.loads((B/'pg-sink-config.json').read_text());config.update({'topics':'eco4pgx.public.eco4_'+name,'collection.name.format':'pg_'+name,'connection.url':f'jdbc:mysql://127.0.0.1:{port}/eco4?useSSL=false&serverTimezone=UTC','connection.password':'111' if port==6001 else 'types-local'})
  cn=f'eco4-pgx-{name}-{port}';api('PUT','/connectors/'+cn+'/config',config);dump(B/(cn+'-config.json'),config)
poll(lambda:all(api('GET','/connectors/'+f'eco4-pgx-{n}-{p}'+'/status')['tasks'] for n,_,_,_ in specs for p in [13306,6001]),60);time.sleep(8)
for name,_,_,_ in specs:
 for port in [13306,6001]:
  cn=f'eco4-pgx-{name}-{port}';r={'type_profile':name,'port':port,'connector':cn}
  try:
   poll(lambda:sql(port,'eco4','SELECT COUNT(*) FROM pg_'+name)[0][0]==3 or any(t['state']=='FAILED' for t in api('GET','/connectors/'+cn+'/status')['tasks']),35)
   r['target_rows']=sql(port,'eco4','SELECT * FROM pg_'+name+' ORDER BY id');r['task_status']=api('GET','/connectors/'+cn+'/status');r['status']='delivered' if len(r['target_rows'])==3 else 'blocked';r['source_rows']=psql('SELECT * FROM eco4_'+name+' ORDER BY id')
   if name=='temporal':
    r['expected_UTC_rows']=psql("SELECT id,clock,zoned AT TIME ZONE 'UTC',flag,day FROM eco4_temporal ORDER BY id")
    expected=[(id,str(clock) if clock is not None else None,zoned,int(flag) if flag is not None else None,day) for id,clock,zoned,flag,day in r['expected_UTC_rows']]
    actual=[(id,str(clock) if clock is not None else None,zoned,int(flag) if flag is not None else None,day) for id,clock,zoned,flag,day in r['target_rows']]
    r['all_fields_equal']=expected==actual;r['status']='passed' if r['all_fields_equal'] else 'failed_fidelity'
   elif name=='varnum':r['all_fields_equal']=r['source_rows']==r['target_rows'];r['status']='passed' if r['all_fields_equal'] else 'failed_fidelity_or_delivery'
  except Exception as e:r['status']='failed';r['error']=str(e)
  out['cases'].append(r);dump(B/'pg-extended-result.json',out);print('PG EXT',name,port,r['status'],flush=True)
