import json,datetime,traceback
from decimal import Decimal
from pathlib import Path
import pyarrow as pa,pymysql
out={'pyarrow':pa.__version__,'cases':[]}
t=pa.table({'id':pa.array([1,2,3],type=pa.int64()),'name':pa.array(['中文','',None],type=pa.string()),'amount':pa.array([Decimal('12.34'),Decimal('-56.78'),None],type=pa.decimal128(18,2)),'ts':pa.array([datetime.datetime(2026,10,10,12,0,0,123456),None,datetime.datetime(2026,10,11,0,0,0)],type=pa.timestamp('us'))})
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True) as d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE arrow_audit')
  for mode in ['file','stream']:
   p=Path(f'arrow-{mode}.arrow').resolve()
   with pa.OSFile(str(p),'wb') as f:
    with (pa.ipc.new_file if mode=='file' else pa.ipc.new_stream)(f,t.schema) as w:w.write_table(t)
   c.execute(f'CREATE TABLE arrow_audit.{mode}_rows(id BIGINT,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))')
   r={'name':'arrow-ipc-'+mode+'-load'}
   try:
    c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='arrow'}} INTO TABLE arrow_audit.{mode}_rows")
    c.execute(f'SELECT * FROM arrow_audit.{mode}_rows ORDER BY id');rows=c.fetchall()
    actual=[[str(v) if v is not None else None for v in row] for row in rows]
    expected=[['1','中文','12.34','2026-10-10 12:00:00.123456'],['2','','-56.78',None],['3',None,None,'2026-10-11 00:00:00']]
    r.update(actual=actual,expected=expected,status='passed' if actual==expected else 'failed')
   except Exception as e:r.update(status='failed',error=str(e))
   out['cases'].append(r)
Path('arrow-load-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
