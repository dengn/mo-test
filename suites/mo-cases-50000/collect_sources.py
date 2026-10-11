import json,urllib.request,time,hashlib,concurrent.futures
from pathlib import Path
P=Path('/workspace/mo-cases-50000');S=P/'sources';S.mkdir(exist_ok=True)
headers={'User-Agent':'MatrixOne-source-backed-test-suite','Accept':'application/vnd.github+json'}
def fetch(url):
    for i in range(3):
        try:return urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45).read()
        except Exception:
            if i==2:raise
            time.sleep(1)
repos=[('matrixorigin/matrixone-doc','main'),('matrixorigin/mo-auto-test','main'),('matrixorigin/mo-nightly-regression','main'),('matrixorigin/mo-benchmark','main'),('matrixorigin/mo-search-lab','main'),('mysql/mysql-server','8.0')]
manifest=[];trees={}
for repo,ref in repos:
    key=repo.replace('/','__');meta=json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/{ref}'));sha=meta['sha']
    tree=json.loads(fetch(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1'));(S/(key+'-tree.json')).write_text(json.dumps(tree));trees[repo]=(sha,tree)
    print(repo,sha,len(tree['tree']),flush=True)
    paths=[e['path'] for e in tree['tree'] if e['type']=='blob']
    chosen=[]
    if repo.endswith('matrixone-doc'):
        for path in paths:
            if not path.startswith('docs/en/MatrixOne/') or not path.endswith('.md'):continue
            if any(k in path for k in ['Functions-and-Operators/Vector/','JSON-Functions/json_','create-fulltext','Vector/vector_type','Vector/vector_search','hnsw-vector-demo','fulltext-boolean-search-demo','Transactions/matrixone-transaction-overview/how-to-use']):chosen.append(path)
        extra=[p for p in paths if p.startswith('docs/en/MatrixOne/Reference/') and p.endswith('.md') and any(k in p.lower() for k in ['string-functions','mathematical','date-and-time','window-functions','group-by','having','joins','case','coalesce','cast','decimal','integer'])]
        chosen+=extra[:35]
    elif repo=='mysql/mysql-server':
        desired=['func_math.test','func_str.test','func_json.test','json.test','func_time.test','type_decimal.test','type_int.test','subselect.test','join.test','group_by.test','window_functions.test','ctype_utf8mb4.test','select.test','insert.test','update.test']
        for name in desired:
            matching=[p for p in paths if p.startswith('mysql-test/t/') and p.endswith('/'+name)]
            chosen+=matching[:1]
        chosen+=['LICENSE','README']
    else:
        chosen=[p for p in paths if p.endswith(('.sql','.test','.py','.md','.yaml')) and any(k in p.lower() for k in ['tpch','ssb','vector','fulltext','sql','query','test','readme'])][:35]
    chosen+=['LICENSE'] if 'LICENSE' in paths and 'LICENSE' not in chosen else []
    def one(path):
        url=f'https://raw.githubusercontent.com/{repo}/{sha}/{path}';dest=S/key/path;dest.parent.mkdir(parents=True,exist_ok=True)
        try:
            data=fetch(url);dest.write_bytes(data);return {'source_id':repo+':'+path,'repo':repo,'commit':sha,'path':path,'url':url,'local_path':str(dest),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'status':'downloaded'}
        except Exception as e:return {'source_id':repo+':'+path,'repo':repo,'commit':sha,'path':path,'url':url,'status':'failed','error':str(e)}
    with concurrent.futures.ThreadPoolExecutor(6) as ex:manifest.extend(ex.map(one,dict.fromkeys(chosen)))
    (P/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print('downloaded',sum(v['status']=='downloaded' and v['repo']==repo for v in manifest),flush=True)
print('total',len(manifest),flush=True)
