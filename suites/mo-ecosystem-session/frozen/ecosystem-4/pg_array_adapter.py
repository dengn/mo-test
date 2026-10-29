from runtime import *
out={'runtime_ref':REF,'scope':'EXPLICIT PG transactional trigger ARRAY->JSONB envelope preserving values, dimensions and lower bounds; DBZ pgoutput/Kafka/JDBC to both targets; not native ARRAY support','cases':[]}
psql('CREATE TABLE eco4_arrays_envelope(id BIGINT PRIMARY KEY,arr JSONB)')
psql("INSERT INTO eco4_arrays_envelope SELECT id,CASE WHEN arr IS NULL THEN NULL ELSE jsonb_build_object('values',to_jsonb(arr),'dimensions',array_dims(arr)) END FROM eco4_arrays")
psql("""CREATE FUNCTION eco4_arrays_mirror() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' THEN DELETE FROM eco4_arrays_envelope WHERE id=OLD.id;RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND OLD.id<>NEW.id THEN DELETE FROM eco4_arrays_envelope WHERE id=OLD.id; END IF;
 INSERT INTO eco4_arrays_envelope VALUES(NEW.id,CASE WHEN NEW.arr IS NULL THEN NULL ELSE jsonb_build_object('values',to_jsonb(NEW.arr),'dimensions',array_dims(NEW.arr)) END) ON CONFLICT(id) DO UPDATE SET arr=EXCLUDED.arr;RETURN NEW;END;$$""")
psql('CREATE TRIGGER eco4_arrays_mirror AFTER INSERT OR UPDATE OR DELETE ON eco4_arrays FOR EACH ROW EXECUTE FUNCTION eco4_arrays_mirror()')
for port in [6001,13306]:sql(port,'eco4','CREATE TABLE pg_arrays_envelope(id BIGINT PRIMARY KEY,arr JSON)')
cfg=json.loads((B/'pg-source-config.json').read_text());cfg.update({'topic.prefix':'eco4pga','slot.name':'eco4_slota','publication.name':'eco4_publicationa','table.include.list':'public.eco4_arrays_envelope'})
api('PUT','/connectors/eco4-pga-source/config',cfg);dump(B/'pg-array-source-config.json',cfg)
for port in [6001,13306]:
 c=json.loads((B/'pg-sink-config.json').read_text());c.update({'topics':'eco4pga.public.eco4_arrays_envelope','collection.name.format':'pg_arrays_envelope','connection.url':f'jdbc:mysql://127.0.0.1:{port}/eco4?useSSL=false&serverTimezone=UTC','connection.password':'111' if port==6001 else 'types-local'})
 api('PUT',f'/connectors/eco4-pga-{port}/config',c);dump(B/f'pg-array-sink-{port}-config.json',c)
def norm(rows):return [(i,json.loads(a) if isinstance(a,str) else a) for i,a in rows]
def check(name,mutation=None):
 if mutation:mutation()
 expected=norm(psql("SELECT id,CASE WHEN arr IS NULL THEN NULL ELSE jsonb_build_object('values',to_jsonb(arr),'dimensions',array_dims(arr)) END FROM eco4_arrays ORDER BY id"))
 for port in [6001,13306]:
  r={'case':name,'port':port,'expected':expected}
  try:
   poll(lambda:norm(sql(port,'eco4','SELECT * FROM pg_arrays_envelope ORDER BY id'))==expected,60)
   r.update({'target':norm(sql(port,'eco4','SELECT * FROM pg_arrays_envelope ORDER BY id')),'status':'passed'})
  except Exception as e:r.update({'status':'failed','error':str(e),'task':api('GET',f'/connectors/eco4-pga-{port}/status')})
  out['cases'].append(r);dump(B/'pg-array-adapter-result.json',out);print('ARRAY ADAPT',name,port,r['status'],flush=True)
check('snapshot_array_NULL_element_empty_array_SQL_NULL')
check('update_lower_bound_and_multidimensional',lambda:psql("UPDATE eco4_arrays SET arr=CASE WHEN id=1 THEN '[0:2]={5,NULL,7}'::integer[] ELSE '{{1,2},{3,NULL}}'::integer[] END WHERE id IN(1,2)"))
check('delete_and_primary_key_migration',lambda:psql('DELETE FROM eco4_arrays WHERE id=3;UPDATE eco4_arrays SET id=20 WHERE id=2'))
