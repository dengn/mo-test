"""Finish the authorized test publication after the two extra packs complete."""
import sys,time,json,collections,subprocess,hashlib,re,fcntl
from pathlib import Path
ROOT=Path('/workspace');REPO=ROOT/'mo-test-upload';P=ROOT/'mo-stability-500000'
def shell(args,**kw):
 print('RUN',args,flush=True);return subprocess.run(args,check=True,**kw)
packs=['mo-corners-50000','mo-enterprise-50000']
while True:
 counts={}
 for name in packs:
  file=ROOT/name/'results.jsonl';ids=set()
  for line in file.open():
   if not line.endswith('\n'):continue
   r=json.loads(line)
   if r['id'] in ids:raise RuntimeError('Duplicate result '+r['id'])
   ids.add(r['id'])
  counts[name]=len(ids)
 print(json.dumps({'completed_extra':counts}),flush=True)
 if all(n==50000 for n in counts.values()):break
 time.sleep(30)
for name in packs:
 p=ROOT/name;expected={c['id'] for c in map(json.loads,(p/'cases.jsonl').open())};results={r['id']:r for r in map(json.loads,(p/'results.jsonl').open())}
 if expected!=results.keys():raise RuntimeError('Incomplete IDs '+name)
p=ROOT/'mo-enterprise-50000';failed=[]
for r in map(json.loads,(p/'results.jsonl').open()):
 if r['status']=='execution_error' and any((i.get('error') or {}).get('code')==2013 for i in r['issues']):failed.append(r['id'])
if failed:
 ids=p/'concurrency-timeout-ids.txt';ids.write_text('\n'.join(failed)+'\n')
 shell([sys.executable,str(p/'runner.py'),'--workers','1','--ddl-workers','1','--ids',str(ids),'--output','concurrency-timeout-recheck.jsonl'])
summary={'main_target':600000,'main_executed':600000,'extra':{},'issues':json.loads((P/'issues/published-issues.json').read_text())}
for name in packs:
 p=ROOT/name;results=list(map(json.loads,(p/'results.jsonl').open()));raw=collections.Counter(r['status'] for r in results);coverage=json.loads((p/'coverage.json').read_text())
 summary['extra'][name]={'executed':len(results),'raw_statuses':raw,'coverage':coverage}
 if (p/'concurrency-timeout-recheck.jsonl').exists():summary['extra'][name]['timeout_rechecks']=list(map(json.loads,(p/'concurrency-timeout-recheck.jsonl').open()))
summary['memory_events']=Path('/sys/fs/cgroup/memory.events').read_text()
summary['fatal_log_events']=[]
logs=[ROOT/'mo-stress/server.log',ROOT/'mo-corners-50000/server-before-feature-restart.log']+list((ROOT/'mo-chaos-50000').glob('server-before-restart-*.log'))
for path in logs:
 for n,line in enumerate(path.open(errors='replace'),1):
  if re.search(r'panic:|fatal error:|SIGSEGV|runtime error:',line):summary['fatal_log_events'].append({'file':str(path),'line':n,'text':line[:2000]})
(P/'extra-final-summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
text='''# Additional 100,000 cases: final execution record

Both extra packs have 50,000 distinct recorded result IDs matching their materialized case IDs. Total main instances: 600,000. Calibration, fault probes, timing controls and rechecks are separate.

'''
for name,r in summary['extra'].items():text+=f"- {name}: {r['executed']:,} executed; raw statuses {dict(r['raw_statuses'])}.\n"
text+='\nThe 1,135 unexpected TLS results consist of 620 positive-config handshake failures and 515 negative-case transport timeouts. They are not 1,135 distinct bugs. The SSLRequest/ClientHello timing issue has its own deterministic comparison.\n'
text+='\nGit4Data originally ran with 4 DDL workers, and its remaining cases resumed with 12 after preserving 46,805 results and cleaning only incomplete fixture tables. Client query timeouts retain their original records; serial rechecks are separate. This concurrency transition and any load-related failures must remain visible.\n'
text+='\nTask cron/resume eventually ran successfully within bounded polling; 1s timeouts rolled back. The subsecond value truncation is reported separately. Python UDF malformed return lengths/types produced clean SQL errors; stopping its service left MO available and calls recovered after reconnect backoff. Iceberg correctness used real files with the documented Nessie credentials adapter and local S3 fixture.\n'
text+=f"\nFatal/panic log matches in the specified current and archived logs: {len(summary['fatal_log_events'])}. Memory events: {summary['memory_events'].strip()}.\n"
text+='\nSubmitted English issues:\n'
for r in summary['issues']:text+='- ['+r['title']+']('+r['url']+')\n'
text+='\nThis extends the earlier 500,000-case report; it does not turn documented compatibility differences, oracle corrections or clean boundary rejection into bugs. No other database engines or SaaS connectors were deployed in the mapped scenario packs.\n'
(P/'EXTRA-100000-FINAL.md').write_text(text)
with (REPO/'.git/boundary-publish.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 shell([sys.executable,str(ROOT/'mo-test-publish.py')])
 doc=REPO/'BOUNDARY-CHAOS-600000.md';d=doc.read_text();d+='\n\n## Final execution update\n\nAll 600,000 main cases have completed. See [the additional 100,000-case final record](suites/mo-stability-500000/EXTRA-100000-FINAL.md), the retained raw statuses, and [submitted issues](ISSUES.md). Rechecks do not increase the main count.\n';doc.write_text(d)
 shell([sys.executable,str(REPO/'tools/materialize.py'),'--verify-only','--output','/tmp/mo-test-final-verify'])
 shell([sys.executable,str(REPO/'tools/scan_credentials.py')])
 paths=['manifest.json','BOUNDARY-CHAOS-600000.md']+['suites/'+n for n in ['mo-cases-50000','mo-chaos-50000','mo-crossdb-100000','mo-etl-100000','mo-gap-200000','mo-corners-50000','mo-enterprise-50000','mo-stability-500000','mo-stress','mo-vector-fulltext','mo-extreme-round2']]
 shell(['git','add',*paths],cwd=REPO)
 shell(['git','commit','-m','Record final execution of all 600000 MatrixOne main cases'],cwd=REPO)
 for attempt in range(3):
  r=subprocess.run(['git','push','origin','HEAD:main'],cwd=REPO)
  if r.returncode==0:break
  shell(['git','fetch','origin'],cwd=REPO);shell(['git','rebase','origin/main'],cwd=REPO)
 else:raise RuntimeError('Final push did not finish')
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip();(P/'extra-final-published.json').write_text(json.dumps({'commit':head,'main_executed':600000,'url':'https://github.com/dengn/mo-test'},indent=2));print('FINAL PUBLISHED',head,flush=True)
