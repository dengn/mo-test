from runtime import *
import gzip,collections
receipt=json.loads((B/'mysql-archive-ownership.json').read_text());path=B/receipt['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256'];digests={};counts=collections.Counter();ddl={}
with gzip.open(path,'rt',encoding='utf8') as f:
 for line in f:
  x=json.loads(line)
  if x['type']=='table':ddl[x['name']]=x['ddl'];digests[x['name']]=hashlib.sha256()
  else:digests[x['table']].update(line.encode());counts[x['table']]+=1
for r in receipt['tables']:assert r['table'] in ddl and counts[r['table']]==r['rows'] and digests[r['table']].hexdigest()==r['sha256'],r['table']
dump(B/'mysql-archive-verification.json',{'status':'passed','tables':len(ddl),'rows':sum(counts.values()),'file_sha256':receipt['sha256'],'checks':'gzipCRC,completefileSHA256,per-tablealltypedrowcounts+SHA256,DDLpresence','no_cleanup_performed':True});print('ARCHIVE VERIFIED',len(ddl),sum(counts.values()),flush=True)
