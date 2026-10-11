import json,urllib.request,hashlib,concurrent.futures
from pathlib import Path
P=Path('/workspace/mo-cases-50000');m=json.loads((P/'source-manifest.json').read_text());old={v['source_id'] for v in m};jobs=[]
for repo in ['matrixorigin/matrixone-doc','matrixorigin/mo-benchmark','matrixorigin/mo-nightly-regression','mysql/mysql-server']:
    key=repo.replace('/','__');tree=json.loads((P/'sources'/(key+'-tree.json')).read_text());sha=next(v['commit'] for v in m if v['repo']==repo);paths=[v['path'] for v in tree['tree'] if v['type']=='blob'];chosen=[]
    if repo.endswith('matrixone-doc'):
        for group in ['Mathematical','String-Functions','Control-Flow','arithmetic-operators','Comparison','select','join','group-by','window','cast','insert','delete','replace','alter-table','constraints','decimal','integer']:
            chosen += [v for v in paths if v.startswith('docs/en/MatrixOne/Reference/') and v.endswith('.md') and group.lower() in v.lower()][:4]
    elif repo.endswith('mo-benchmark'):chosen=[v for v in paths if v in ['clickbench/mysql/create.sql','clickbench/mysql/queries.sql','clickbench/matrixone/create.sql','clickbench/matrixone/queries.sql']]
    elif repo.endswith('mo-nightly-regression'):chosen=['script/fulltext2_stability/oracle.py','script/fulltext2_stability/harness.py','script/test_vector_recall_checker.py','script/test_vector_index_auto_update_contract.py']
    else:chosen=[v for v in paths if v.startswith('mysql-test/t/') and v.endswith('.test') and 'json' in v.lower()][:6]
    for path in dict.fromkeys(chosen):
        if repo+':'+path not in old:jobs.append((repo,sha,path))
def one(x):
    repo,sha,path=x;url=f'https://raw.githubusercontent.com/{repo}/{sha}/{path}';data=urllib.request.urlopen(url,timeout=40).read();local=P/'sources'/repo.replace('/','__')/path;local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data);return {'source_id':repo+':'+path,'repo':repo,'commit':sha,'path':path,'url':url,'local_path':str(local),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'status':'downloaded'}
with concurrent.futures.ThreadPoolExecutor(6) as e:m.extend(e.map(one,jobs))
(P/'source-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print('sources',len(m))
