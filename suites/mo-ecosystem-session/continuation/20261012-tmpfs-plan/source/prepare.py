"""Prepare an isolated alternative. No server startup or SQL mutation here."""
from pathlib import Path
import json,shutil,hashlib,uuid,tomllib,os,datetime,py_compile
B=Path(__file__).resolve().parent;OLD=Path('/workspace/work/heavy-5000');SRC=OLD/'windowed';D=B/'windowed';D.mkdir(exist_ok=True)
for p in SRC.glob('*.py'):shutil.copyfile(p,D/p.name)
for n in ['table-reuse-review-plan.json','table-reuse-approval.json']:shutil.copyfile(OLD/n,B/n)
out=B/'results';(out/'core-results').mkdir(parents=True,exist_ok=True)
shutil.copyfile(OLD/'windowed-results/core-results/pandas.jsonl',out/'core-results/pandas.jsonl')
rows=[json.loads(l) for l in (out/'core-results/pandas.jsonl').read_text().splitlines()];assert len(rows)==2431 and len({r['id'] for r in rows})==2431 and all(r['status']=='passed' for r in rows)
identity='heavy-alt-'+uuid.uuid4().hex[:10];C=B/'config';C.mkdir(exist_ok=True);source=Path('/workspace/work/pressure-5/mo-config')
for p in source.glob('*.toml'):
 text=p.read_text().replace('/workspace/work/path-verification/runtime/mo-data',str(B/'runtime/mo-data')).replace(str(source),str(C)).replace('bucket = "mo-test"','bucket = "'+identity+'"').replace('http://127.0.0.1:9000','http://127.0.0.1:9002').replace('memory-capacity = "512MB"','memory-capacity = "128MB"').replace('disk-capacity = "256MB"','disk-capacity = "64MB"').replace('port = 6001','port = 16001').replace('status-port = 7001','status-port = 17001')
 for old in ['dd1dccb4-4d3c-41f8-b482-5251dc7a41bf','713F97B0-1E28-4F80-849D-FE0979AE734A']:text=text.replace(old,str(uuid.uuid4()))
 assert '/workspace/work/' not in text and 'http://127.0.0.1:9000' not in text
 tomllib.loads(text);(C/p.name).write_text(text)
# Future receipts record runtime identity as well as logical role so that old
# archived successes remain distinguishable from new physical endpoints.
p=D/'run_windows_micro.py';text=p.read_text();text=text.replace("r['database']=DS;r['window_profile']=p['name']","r['database']=DS;r['window_profile']=p['name'];r['runtime_id']=os.environ['MO_CASE_RUNTIME_ID'];r['actual_endpoint']=endpoint(r['port'])['port']")
assert "r['runtime_id']" in text;p.write_text(text)
p=D/'runtime.py';text=p.read_text();needle=' return free\ndef percentile'
assert needle in text
text=text.replace(needle,""" # All data/outputs share the distinct tmpfs; do not use the full root fs.
 usage=shutil.disk_usage(B)
 if usage.total-usage.free>4*1024**3:raise RuntimeError('test resource guard: temporary filesystem usage exceeds4GiB')
 m={x.split()[0]:int(x.split()[1]) for x in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines()}
 limit=int(Path('/sys/fs/cgroup/memory.max').read_text())
 unavailable=sum(m.get(x,0) for x in ['anon','shmem','kernel','file_dirty','file_writeback','unevictable'])
 if limit-unavailable<3*1024**3:raise RuntimeError('test resource guard: less than3GiB estimated memory headroom after reclaimable file cache')
 return free
def percentile""")
p.write_text(text)
for p in D.glob('*.py'):py_compile.compile(str(p),doraise=True)
routes=['pandas','sqlalchemy','pymysql','mysql_connector','polars','dask','duckdb_parquet_bridge','arrow_ipc_bridge']
plan={'status':'prepared_not_started_requires_scope_change_approval','runtime_id':identity,'directory':str(B),'database':'mo_ecosystem_heavy_20261012','actual_endpoints':{'MO':16001,'MySQL':23306,'MinIO':9002},'source_binaries':'Read-only copies from existing containers, same MO binary; no new Docker container/pull','MO_source_commit':'652c643666428f1c434e03369834f2a9bead7c27','MySQL_version':'8.4.11','first_route':'pandas','first_route_completed_before':2431,'first_route_pending':2569,'next_core_routes':routes[1:],'core_pending_cases':37569,'all_main_pending_cases':127569,'workers':2,'max_cases_per_window':20,'min_tmp_free_bytes':2*1024**3,'max_tmp_filesystem_used_bytes':4*1024**3,'min_estimated_memory_headroom_bytes':3*1024**3,'MO_soft_Go_memory_limit':'1536MiB','MinIO_soft_Go_memory_limit':'256MiB','MySQL_buffer_pool':'128MiB','MySQL_redo_capacity':'64MiB','case_oracles':'Unchanged logical IDs, physical32-256rows and datatype/scenario/seed definitions; future results have runtime_id/physical ports; full typed archive + independent readback + hash before SQL scratch-table reuse','cleanup':'Only registered newly created scratch SQL tables in this new runtime after verified full archive; no old tables/directories/buckets/log deletion; no filesystem/S3 cleanup','scope_change':'Uses memory-backed temporary filesystem instead of waiting for64GiB durable disk expansion. No disk-throughput or long-soak certification claim; pause at capacity/memory guards','timestamp_Asia_Shanghai':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
(B/'review-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
(B/'execution-approval.json').write_text(json.dumps({'approved':False,'reason':'Previous user explicitly chose64GiB expansion beforeheavywrites; alternative tmpfs execution needs explicit change of scope'},ensure_ascii=False,indent=2)+'\n')
files={p.relative_to(B).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for root in [D,C] for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
(B/'prepared-source-manifest.json').write_text(json.dumps(files,indent=2)+'\n')
print(json.dumps(plan,ensure_ascii=False))
