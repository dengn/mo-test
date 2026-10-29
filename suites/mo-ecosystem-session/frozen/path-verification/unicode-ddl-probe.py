import pymysql,json
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','database':'unicode_native_probe','cases':[]}
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True,use_unicode=False) as d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE unicode_native_probe')
  for name,sql,expected in [('unquoted-latin-unicode', 'CREATE TABLE unicode_native_probe.t_ãg(id INT)','745FC3A367'),('quoted-latin-unicode','CREATE TABLE unicode_native_probe.`quoted_ãg`(id INT)','71756F7465645FC3A367'),('unquoted-chinese','CREATE TABLE unicode_native_probe.t_表(id INT)','745FE8A1A8')]:
   r={'name':name,'sql':sql,'wire_utf8_hex':sql.encode('utf8').hex(),'expected_table_name_hex':expected}
   try:c.execute(sql);r['status']='accepted'
   except Exception as e:r.update(status='failed',error=str(e))
   out['cases'].append(r)
  c.execute("SELECT hex(relname) FROM mo_catalog.mo_tables WHERE reldatabase='unicode_native_probe' ORDER BY relname");out['actual_table_name_hex']=[r[0].decode('ascii') for r in c.fetchall()]
  try:c.execute('DROP DATABASE unicode_native_probe');out['drop_database']={'status':'passed'}
  except Exception as e:out['drop_database']={'status':'failed','error':str(e)[:1800]}
open('unicode-ddl-result.json','w').write(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
