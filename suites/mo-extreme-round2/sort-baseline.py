import json,time,pymysql
from pathlib import Path
p=Path('/workspace/mo-extreme-round2');name=(p/'database.txt').read_text().strip();c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=name,autocommit=True,read_timeout=90,connect_timeout=5)
t=time.time()
try:
 with c.cursor() as q:
  q.execute('SELECT id FROM bulk ORDER BY payload LIMIT 100000');rows=q.fetchall();ids=[int(r[0]) for r in rows];good=len(ids)==100000 and len(set(ids))==100000 and all(1<=i<=200000 for i in ids)
 r={'type':'sort_baseline','workers':1,'pass':good,'rows_returned':len(ids),'elapsed_seconds':time.time()-t}
except Exception as e:r={'type':'sort_baseline','workers':1,'pass':False,'elapsed_seconds':time.time()-t,'error':str(e)}
finally:c.close()
(p/'sort-baseline.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
