from heavy import *
path=B/'core-results/petl.jsonl';rows=[json.loads(l) for l in path.read_text().splitlines()];checks=[]
for p in PROFILES:
 for port in [6001,13306]:
  subset=[r for r in rows if r['profile']==p['name'] and r['port']==port]
  if not subset:continue
  t,_=tables('petl',p);actual=sql('SELECT case_id,id,v,label,rev FROM '+t+' WHERE case_id<100000 ORDER BY case_id,id',port=port);byid=collections.defaultdict(list)
  for row in actual:byid[row[0]].append(row)
  for receipt in subset:
   values=canon(byid[receipt['logical_case_id']],p);checks.append({'id':receipt['id'],'status':'passed' if sha(values)==receipt['expected_sha256'] and len(values)==receipt['expected_rows'] else 'failed','actual_rows':len(values),'actual_sha256':sha(values)})
assert all(c['status']=='passed' for c in checks);dump(B/'paused-runtime-full-readback.json',{'checked':len(checks),'counts':dict(collections.Counter(c['status'] for c in checks)),'scope':'All recordedcases independently reread from old preserved namespace; unfinished futures no receipts and will retry','checks':checks});print(len(checks),dict(collections.Counter(c['status'] for c in checks)),flush=True)
