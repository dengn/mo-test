from heavy import *
import gzip,struct
# Read-only preparation: archive exact current-round fixture tables before requesting reuse/cleanup.
allowed={table for route in ROUTES for p in PROFILES for table in list(tables(route,p))+['e_'+route.split('_')[0]+'_'+p['name']]}
def enc(v):
 if isinstance(v,decimal.Decimal):return {'kind':'decimal','value':str(v)}
 if isinstance(v,datetime.datetime):return {'kind':'datetime','value':v.isoformat()}
 if isinstance(v,datetime.date):return {'kind':'date','value':v.isoformat()}
 if isinstance(v,datetime.timedelta):return {'kind':'duration','value':(v.days*86400+v.seconds)*1000000+v.microseconds}
 if isinstance(v,(bytes,bytearray)):return {'kind':'bytes','value':bytes(v).hex()}
 if isinstance(v,(set,frozenset)):return {'kind':'set','value':sorted(v)}
 return v
out=B/'mysql-current-round-fixtures.jsonl.gz';inventory=[]
with db(13306) as d,d.cursor() as c:c.execute('SHOW TABLES');existing={r[0] for r in c.fetchall()}
with gzip.open(out,'wt',encoding='utf8',compresslevel=3) as f:
 for t in sorted(allowed & existing):
  with db(13306) as d,d.cursor() as c:
   c.execute('SHOW CREATE TABLE '+t);ddl=c.fetchone()[1];c.execute('SELECT * FROM '+t+' ORDER BY case_id,id');rr=c.fetchall();columns=[r[0] for r in c.description];assert columns[:5]==COLS,columns
   # Verify this task's generated identities and labels. No tables outside explicit plan are selected.
   for r in rr:assert 0<int(r[0])<110000 and str(r[3]).startswith(('租户','复杂更新','复杂新增','删除标记','删除后重插')),('unrecognized fixture',t,r[:2])
   f.write(json.dumps({'type':'table','name':t,'ddl':ddl,'columns':columns},ensure_ascii=False)+'\n');digest=hashlib.sha256()
   for r in rr:
    line=json.dumps({'type':'row','table':t,'row':[enc(v) for v in r]},ensure_ascii=False,separators=(',',':'));f.write(line+'\n');digest.update((line+'\n').encode())
   inventory.append({'table':t,'rows':len(rr),'sha256':digest.hexdigest()})
  print('ARCHIVED',t,len(rr),flush=True)
receipt={'file':out.name,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'tables':inventory,'total_rows':sum(r['rows'] for r in inventory),'scope':'Only MySQL heavy5000 exact allowlistedtables createdbythisround; fullDDL+typedrows archived,labels/caseIDs verified. No prior-round databases, MO state directories or S3 buckets are selected. Readonly preparation; no deletionperformed.'};dump(B/'mysql-archive-ownership.json',receipt);print('DONE',receipt['total_rows'],receipt['bytes'],flush=True)
