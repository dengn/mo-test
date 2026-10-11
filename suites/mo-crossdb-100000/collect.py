import urllib.request,json,concurrent.futures,hashlib,time
from pathlib import Path
P=Path(__file__).resolve().parent
repos={'doris':'apache/doris-website','starrocks':'StarRocks/starrocks','tidb':'pingcap/docs','clickhouse':'ClickHouse/clickhouse-docs','tdengine':'taosdata/TDengine','milvus':'milvus-io/milvus-docs'}
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MO-crossdb-test-research'})
 for attempt in range(3):
  try:return urllib.request.urlopen(req,timeout=50).read()
  except Exception:
   if attempt==2:raise
   time.sleep(attempt+1)
manifest=[]
for engine,repo in repos.items():
 info=json.loads(get('https://api.github.com/repos/'+repo));branch=info['default_branch'];commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/'+branch))['sha'];tree=json.loads(get('https://api.github.com/repos/'+repo+'/git/trees/'+commit+'?recursive=1'))
 (P/(engine+'-tree.json')).write_text(json.dumps(tree));paths=[x['path'] for x in tree['tree'] if x['type']=='blob' and x['path'].lower().endswith(('.md','.mdx'))]
 english=[p for p in paths if not any(x in p.lower() for x in ['/zh/','/zh-cn/','/cn/','/ja/','/ko/','/ru/','/de/','/fr/','/es/'])]
 keywords=['unique','primary_key','aggregate','aggregation','partition','join','window','json','array','vector','hybrid','full-text','fulltext','search','time-series','time_series','interval','stream','transaction','upsert','delete','null','group-by','order-by','filter','ttl','schemaless','scalar','dynamic','consistency','distribut','materialized']
 selected=[]
 for word in keywords:
  hit=[p for p in english if word in p.lower() and ('docs/' in p.lower() or engine in ['tidb','milvus'])];hit.sort(key=lambda p:(('/en/' not in p),('version-' in p),len(p),p));selected.extend(hit[:2])
 selected=list(dict.fromkeys(selected))[:45]
 if not selected:selected=english[:30]
 for lic in ['LICENSE','LICENSE.md','LICENSE.txt']:
  if any(x['path']==lic for x in tree['tree']):selected.append(lic);break
 print(engine,branch,commit,'selected',len(selected),flush=True)
 def download(path):
  url=f'https://raw.githubusercontent.com/{repo}/{commit}/{path}';data=get(url);local=P/'sources'/engine/path;local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data)
  return {'engine':engine,'repo':repo,'commit':commit,'branch':branch,'path':path,'url':url,'local_path':str(local),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'source_id':repo+':'+path}
 with concurrent.futures.ThreadPoolExecutor(6) as ex:
  for f in ex.map(download,selected):manifest.append(f)
 (P/'source-manifest.json').write_text(json.dumps(manifest,indent=2))
print('downloaded',len(manifest),flush=True)
