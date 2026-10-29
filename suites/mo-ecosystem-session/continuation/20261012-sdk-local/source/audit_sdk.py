import json,pathlib,sys,collections,hashlib
import duckdb
B=pathlib.Path(__file__).resolve().parent;P=B/'fivetran-project';stage=sys.argv[1]
jobs=json.loads((P/'fixtures.json').read_text());con=duckdb.connect(str(P/'files/warehouse.db'),read_only=True)
ts=con.execute('SHOW ALL TABLES').fetchall();t=next(x for x in ts if x[2]=='ecosystem_sdk_preflight');name='"'+t[1]+'"."'+t[2]+'"'
cols=[x[0] for x in con.execute('SELECT * FROM '+name+' LIMIT 0').description]
rows=con.execute('SELECT * FROM '+name+' ORDER BY endpoint,case_id,row_id').fetchall();items=[dict(zip(cols,r)) for r in rows]
by=collections.defaultdict(list);keys=set()
for r in items:
 k=(r['endpoint'],r['case_id'],r['row_id']);assert k not in keys;keys.add(k);by[r['case_id']].append(r)
out=[]
for c in jobs:
 original={r[1]:r.copy() for r in c['source_rows']};expected={i:r.copy() for i,r in original.items()};tombs=set()
 if c['scenario']=='sparse_update':
  for i,r in expected.items():
   if i%3==0:r[3]+='→SDK更新';r[4]+=10
 if c['scenario']=='delete_reinsert':
  for i in original:
   if i%4==3:del expected[i];tombs.add(i)
   elif i%4==1:expected[i][3]+='→删除后重插';expected[i][4]+=2
 physical=by[c['case_id']];active={r['row_id']:r for r in physical if not r['_fivetran_deleted']};actual_dead={r['row_id'] for r in physical if r['_fivetran_deleted']};errors=[]
 if set(active)!=set(expected):errors.append('active key mismatch')
 if actual_dead!=tombs:errors.append('tombstone key mismatch')
 if len(physical)!=len(original):errors.append('physical replay key count mismatch')
 for i,e in expected.items():
  if i not in active:continue
  a=active[i]
  if json.loads(a['payload'])!=e or a['rev']!=e[4]:errors.append('payload/rev mismatch id'+str(i))
  if a['profile']!=c['profile'] or a['scenario']!=c['scenario'] or a['endpoint']!=c['endpoint']:errors.append('sparse-update retained field mismatch')
  if stage in ['evolved','noop'] and a.get('schema_epoch')!='v2':errors.append('schema epoch mismatch')
 expected_rows=[expected[i] for i in sorted(expected)];actual_rows=[json.loads(active[i]['payload']) for i in sorted(active)]
 sha=lambda v:hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
 out.append({'id':c['id'],'profile':c['profile'],'endpoint':c['endpoint'],'scenario':c['scenario'],'stage':stage,'status':'passed' if not errors else 'fidelity_failed','errors':errors,'expected_rows':len(expected),'actual_rows':len(active),'tombstone_rows':len(actual_dead),'expected_sha256':sha(expected_rows),'actual_sha256':sha(actual_rows),'scope':'Official SDK local tester->DuckDB; archived source; STRING envelope; no live MO destination/SaaS/EOS certification'})
con.close();counts=dict(collections.Counter(r['status'] for r in out));canonical=json.dumps(items,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':'))
(B/f'results-{stage}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out))
summary={'stage':stage,'checked':len(out),'counts':counts,'physical_rows':len(items),'active_rows':sum(not r['_fivetran_deleted'] for r in items),'tombstones':sum(bool(r['_fivetran_deleted']) for r in items),'duplicate_keys':0,'columns':cols,'durable_state':json.loads((P/'files/state.json').read_text()),'warehouse_values_sha256':hashlib.sha256(canonical.encode()).hexdigest()}
(B/f'audit-{stage}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
assert counts=={'passed':200},counts
