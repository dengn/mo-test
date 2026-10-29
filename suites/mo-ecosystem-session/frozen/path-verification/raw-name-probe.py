import json,pymysql
out={'name':'raw-non-utf8-identifier-admission-and-drop','matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','sql_wire_hex':b'CREATE TABLE raw_name_probe.t_\xe3g(id INT)'.hex()}
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True,use_unicode=False) as d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE raw_name_probe')
  try:c.execute(b'CREATE TABLE raw_name_probe.t_\xe3g(id INT)');out['admission']='accepted'
  except Exception as e:out.update(admission='rejected',admission_error=str(e))
  c.execute("SELECT hex(relname) FROM mo_catalog.mo_tables WHERE reldatabase='raw_name_probe'");out['actual_name_hex']=[r[0].decode('ascii') for r in c.fetchall()]
  try:c.execute('DROP DATABASE raw_name_probe');out['drop']='passed'
  except Exception as e:out.update(drop='failed',drop_error=str(e)[:2200])
open('raw-name-result.json','w').write(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
