"""Freeze authored cases/evidence into the user's mo-test checkout without runtimes."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil

P=Path(__file__).resolve().parent
ROOT=Path('/workspace/mo-test-upload')
TARGET=ROOT/'suites/mo-gis-app-projects'
TTL=Path('/workspace/mo-ttl-check')
tokens=set();redactions=[]
def strings(obj):
    if isinstance(obj,str):yield obj
    elif isinstance(obj,dict):
        for v in obj.values():yield from strings(v)
    elif isinstance(obj,list):
        for v in obj:yield from strings(v)
# Gather session CSRF values from captured HTTP forms, never publish their values.
for f in P.glob('*.json'):
    try:j=json.loads(f.read_text())
    except (ValueError,UnicodeDecodeError):continue
    for s in strings(j):
        for m in re.finditer(r'csrfmiddlewaretoken[\s\S]{0,40}?value=[\"\x27]([A-Za-z0-9]{32,64})',s):tokens.add(m.group(1))
def freeze(src,dst):
    data=src.read_bytes();n=0
    if src.suffix in {'.json','.jsonl','.log','.txt','.md','.py','.yml','.toml','.html','.xml','.umap'}:
        text=data.decode('utf-8')
        for token in tokens:
            n+=text.count(token);text=text.replace(token,'[REDACTED_LOCAL_CSRF_TOKEN]')
        text,count=re.subn(r'(Debugger PIN:)\s*[0-9][0-9-]{4,}',r'\1 [REDACTED_LOCAL_DEBUGGER_PIN]',text);n+=count
        data=text.encode()
    dst.parent.mkdir(parents=True,exist_ok=True)
    if len(data)>1_000_000 and src.suffix in {'.json','.jsonl','.log','.txt'}:
        dst=dst.with_name(dst.name+'.gz');dst.write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
    else:dst.write_bytes(data)
    if n:redactions.append({'path':str(dst.relative_to(ROOT)),'redacted_values':n})

assert not TARGET.exists(),'Do not overwrite a previously published suite'
TARGET.mkdir(parents=True)
extensions={'.py','.js','.json','.jsonl','.log','.md','.txt','.yml','.png','.qgz','.gpkg','.xml','.umap'}
for f in sorted(P.iterdir()):
    if f.is_file() and f.suffix in extensions:freeze(f,TARGET/f.name)
for directory in ['config','issues','geoserver-images']:
    for f in sorted((P/directory).rglob('*')):
        if f.is_file():freeze(f,TARGET/f.relative_to(P))
for f in sorted((P/'adapters/java').rglob('*.java')):freeze(f,TARGET/f.relative_to(P))
freeze(P/'adapters/build_geoserver_adapter.py',TARGET/'adapters/build_geoserver_adapter.py')
for f in sorted((P/'research').iterdir()):
    if f.suffix in {'.java','.py','.toml','.txt','.json'}:freeze(f,TARGET/f.relative_to(P))
for f in sorted((P/'maputnik-styles').glob('*.json')):freeze(f,TARGET/f.relative_to(P))
freeze(P/'pygeoapi-static/local-tile.png',TARGET/'pygeoapi-static/local-tile.png')
# License snapshots accompany source references; full third-party packages aren't copied.
for name in ['pygeoapi','umap','maputnik']:
    for f in sorted((P/'projects'/name).glob('LICENSE*')):
        if f.is_file():freeze(f,TARGET/'upstream-licenses'/name/f.name)
freeze(P/'projects/geoserver/LICENSE.html',TARGET/'upstream-licenses/geoserver/LICENSE.html')
ttl_target=ROOT/'suites/mo-ttl-check';assert not ttl_target.exists();ttl_target.mkdir(parents=True)
for f in sorted(TTL.iterdir()):
    if f.is_file() and f.suffix in {'.py','.json','.log','.md'}:freeze(f,ttl_target/f.name)

publication={'redactions':redactions,'redacted_token_values_not_in_report':True,
    'excluded':['projects and vendor runtimes','python-env','node_modules/npm-cache','downloads','database data',
                'cache/PID files','compiled adapters','runtime GeoServer security material','session cookies','RTL dependency script'],
    'raw_evidence_location':str(P),'note':'Inputs/results retained; only actual local CSRF values and debugger PINs redacted. Synthetic local database/app passwords are reproducible fixture values.'}
(TARGET/'publication-redactions.json').write_text(json.dumps(publication,indent=2)+'\n')
manifest=json.loads((ROOT/'manifest.json').read_text())
summary=json.loads((P/'workflow-summary.json').read_text())
manifest['followup_probes']['gis_open_source_applications']={'path':'suites/mo-gis-app-projects/README.md',
    'mo_commit':summary['runtime_matrixone_commit'],'applications':5,'workflow_attempt_records':summary['workflow_attempt_records'],
    'unique_project_engine_phase_workflows':summary['unique_workflows'],'latest_outcomes':summary['final_statuses'],
    'native_failures_preserved':True,'confirmed_new_MO_issues':[30046],'panic_observed':False,'main_count_contribution':0,'state':'complete'}
manifest['followup_probes']['ttl_capability']={'path':'suites/mo-ttl-check/README.md','native_row_table_ttl':False,
    'scheduled_cleanup_verified':True,'unsupported_syntax_probes':6,'behavioral_checks':4,'main_count_contribution':0,'state':'complete'}
for directory,kind in [(TARGET,'gis_open_source_application_evidence'),(ttl_target,'ttl_capability_evidence')]:
    for f in sorted(directory.rglob('*')):
        if f.is_file():manifest['files'].append({'path':str(f.relative_to(ROOT)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'kind':kind})
assert manifest['main_case_count']==600000
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
readme=ROOT/'README.md'
readme.write_text(readme.read_text()+'\n\n## 五个开源 GIS 应用与 TTL 能力核验\n\n'
    +'[GeoServer、pygeoapi、QGIS、uMap、Maputnik 的真实端到端测试](suites/mo-gis-app-projects/README.md)：51 个项目/后端/接入阶段工作流，保留原生失败与适配后结果；新增确认的几何协议缺陷 [#30046](https://github.com/matrixorigin/matrixone/issues/30046)。\n\n'
    +'[TTL 源码、文档与 SQL 实测](suites/mo-ttl-check/README.md)：当前 main 无原生行/表 TTL，定时 SQL task 删除过期行已验证。两套后续核验均不计入原有 600,000 条主 case。\n')
print(json.dumps({'files_added':sum(1 for d in [TARGET,ttl_target] for f in d.rglob('*') if f.is_file()),'redacted_files':len(redactions),'main_cases':manifest['main_case_count']}))
