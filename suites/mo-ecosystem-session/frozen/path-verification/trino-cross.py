import json,time,traceback
from pathlib import Path
import trino,pymysql,requests
out={'trino_version':'476','image_digest':'sha256:00125e40d063bc4816d165482f6044872b18b56026fb959d3b28ce1f96ffbbee','cases':[]}
def norm(rs):return [[str(v) if v is not None else None for v in r] for r in rs]
def check(name,rs,expected):
 a=norm(rs);out['cases'].append({'name':name,'actual':a,'expected':expected,'status':'passed' if a==expected else 'failed'});assert a==expected,(name,a,expected)
db=None;tdb=None
try:
 deadline=time.monotonic()+60
 while True:
  try:
   p=requests.get('http://127.0.0.1:18082/v1/info',timeout=2)
   if p.ok and not p.json().get('starting',True):break
  except requests.RequestException:pass
  if time.monotonic()>deadline:raise TimeoutError('Trino not ready after 60 seconds')
  time.sleep(1)
 tdb=trino.dbapi.connect(host='127.0.0.1',port=18082,user='audit',catalog='iceberg',schema='mo_audit_cross')
 c=tdb.cursor();c.execute('SELECT * FROM cross_rows ORDER BY id')
 expected=[['1','Spark 中文','12.34','2026-10-10'],['2',None,'56.78','2026-10-11'],['3','MO 中文','90.12','2026-10-12']]
 check('spark-and-mo-write-trino-read',c.fetchall(),expected)
 c.execute("INSERT INTO cross_rows VALUES (4,'Trino 中文',CAST(34.56 AS DECIMAL(18,2)),DATE '2026-10-13')");c.fetchall()
 expected.append(['4','Trino 中文','34.56','2026-10-13'])
 db=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)
 with db.cursor() as mc:mc.execute('SELECT * FROM cross_audit.cross_rows ORDER BY id');check('trino-write-mo-read',mc.fetchall(),expected)
 out['status']='passed'
except Exception as e:out.update(status='failed',error=str(e));traceback.print_exc()
finally:
 if db:db.close()
 if tdb:tdb.close()
 Path('trino-cross-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if out['status']!='passed':raise SystemExit(1)
