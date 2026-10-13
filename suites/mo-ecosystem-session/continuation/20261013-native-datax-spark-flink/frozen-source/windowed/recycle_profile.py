"""Archive/verify NEW owned SQL scratch windows. Apply requires explicit approval."""
from runtime import *
import argparse,gzip,re,uuid

def sha_bytes(data):return hashlib.sha256(data).hexdigest()
def encode(v):
 if v is None:return ['null']
 if isinstance(v,(bytes,bytearray,memoryview)):return ['bytes',bytes(v).hex()]
 if isinstance(v,decimal.Decimal):return ['decimal',str(v)]
 if isinstance(v,datetime.datetime):return ['datetime',v.isoformat(timespec='microseconds')]
 if isinstance(v,datetime.date):return ['date',v.isoformat()]
 if isinstance(v,datetime.timedelta):return ['time_us',(v.days*86400+v.seconds)*1000000+v.microseconds]
 if isinstance(v,float):return ['float_hex',v.hex()]
 if isinstance(v,(set,frozenset)):return ['set',sorted(v)]
 return ['scalar',v]
def snapshot(role,table):
 with db(role) as d,d.cursor() as c:
  c.execute('SHOW CREATE TABLE `'+table+'`');ddl=c.fetchone()[1]
  c.execute('SELECT * FROM `'+table+'` ORDER BY case_id,id');columns=[x[0] for x in c.description]
  h=hashlib.sha256();rows=[]
  for row in c.fetchall():
   assert 1<=int(row[0])<=2500 or 100001<=int(row[0])<=102500,'foreign case identifier'
   item=[encode(v) for v in row];data=json.dumps(item,ensure_ascii=False,separators=(',',':')).encode()+b'\n';h.update(data);rows.append(item)
 return {'endpoint':role,'database':DS,'table':table,'ddl':ddl,'columns':columns,'rows':rows,'row_sha256':h.hexdigest(),'row_count':len(rows)}
def registry():
 p=B/'created-table-registry.json'
 return p,json.loads(p.read_text()) if p.exists() else {'database':DS,'tables':[]}
def register(role,table,route,profile):
 assert DS=='mo_ecosystem_heavy_20261012','Existing schemas are excluded'
 verify_ownership()
 assert re.fullmatch(r'[tse]_[a-z0-9_]+',table)
 plan=json.loads((Path(__file__).parents[1]/'table-reuse-review-plan.json').read_text())
 assert any(x['table']==table and x['route']==route and x['profile']==profile for x in plan['tables'])
 path,r=registry();assert r['database']==DS
 if not any(x['endpoint']==role and x['table']==table for x in r['tables']):
  record=snapshot(role,table)
  # Registration is allowed only immediately after this program creates an
  # empty table. Foreign existing data cannot be adopted into the cleanup set.
  assert record['row_count']==0,'Refusing to adopt nonempty preexisting scratch table'
  r['tables'].append({'endpoint':role,'table':table,'route':route,'profile':profile,'creation_ddl':record['ddl'],'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  dump(path,r)
def archive_profile(route,profile,apply=False):
 assert DS=='mo_ecosystem_heavy_20261012';verify_ownership();_,r=registry()
 entries=[x for x in r['tables'] if x['route']==route and x['profile']==profile]
 assert entries and all(x['endpoint'] in [6001,13306] for x in entries)
 snapshots=[snapshot(x['endpoint'],x['table']) for x in entries]
 target=B/'window-archives';target.mkdir(exist_ok=True)
 name=target/(route+'_'+profile+'_'+uuid.uuid4().hex[:10]+'.json.gz')
 raw=json.dumps({'database':DS,'route':route,'profile':profile,'tables':snapshots},ensure_ascii=False,separators=(',',':')).encode()
 compressed=gzip.compress(raw,compresslevel=9,mtime=0);name.write_bytes(compressed)
 with name.open('rb') as f:os.fsync(f.fileno())
 restored=json.loads(gzip.decompress(name.read_bytes()))
 assert restored['tables']==snapshots
 for table in restored['tables']:
  h=hashlib.sha256()
  for row in table['rows']:h.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n')
  assert h.hexdigest()==table['row_sha256'] and len(table['rows'])==table['row_count']
 receipt={'database':DS,'route':route,'profile':profile,'archive':str(name),'sha256':sha_bytes(name.read_bytes()),
  'bytes':len(compressed),'tables':[{'endpoint':x['endpoint'],'table':x['table'],'rows':x['row_count'],'row_sha256':x['row_sha256']} for x in snapshots],
  'archive_verified':True,'applied':False,'excluded':'All existing databases/directories/buckets/services'}
 if apply:
  approval=Path(__file__).parents[1]/'table-reuse-approval.json'
  assert approval.exists() and json.loads(approval.read_text()).get('approved') is True,'User approval has not been received'
  # Retest full contents/DDL immediately before deleting any completed window.
  for old in snapshots:
   now=snapshot(old['endpoint'],old['table']);assert now==old,'Scratch window changed after archive; refusing deletion'
  for x in snapshots:sql('DROP TABLE `'+x['table']+'`',port=x['endpoint'])
  receipt['applied']=True
 dump(name.with_suffix('.receipt.json'),receipt)
 return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--profile',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 print(json.dumps(archive_profile(a.route,a.profile,a.apply),ensure_ascii=False))
