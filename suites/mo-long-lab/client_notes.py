"""Keep planner limits and incomplete attempts separate from MO outcomes."""
import collections,json
from data import ROOT
def attempt(folder):
 p=ROOT/'results'/folder;r={}
 if (p/'cases.jsonl').exists():r['output_assertions']=dict(collections.Counter(json.loads(l)['status'] for l in (p/'cases.jsonl').open()))
 for file in ['meta.json','jobs.json','block-checks.json']:
  if (p/file).exists():r[file]=json.loads((p/file).read_text())
 return r
notes={
 'counting':'Only canonical 50×200 belongs to the requested 10000. Supplemental 2×1000 output checks per completed engine variant are separate. Incomplete planner attempts do not create successful/failed MO SQL cases.',
 'spark_default_analyzer':{'classification':'Spark client Resolution iteration cap, not MO server error','setting':100,'evidence':attempt('spark-default-iterations')},
 'spark_tuned':{'classification':'Completed JDBC pipelines after client configuration adjustment','setting':500,'isolation':'READ_COMMITTED','evidence':attempt('spark')},
 'flink_identifier_pilot':{'classification':'Flink Calcite reserved identifiers; quoted harness identifiers before retry','evidence':attempt('flink-harness-identifiers')},
 'flink_monolithic':{'classification':'Incomplete planning; explicitly terminated test-owned Python/JVM after excessive memory/time. No result equivalence claim; not a natural crash or proven MO defect.','resource_evidence':'flink-resource-limit.json','log':'flink-quoted.log'},
 'flink_features_only':{'classification':'Six feature outputs matched, but downstream scoring planning crossed the configured client RSS guard. Incomplete final pipeline; no 2000-case success claim.','guard':json.loads((ROOT/'flink_staged-guard.json').read_text()),'log':'flink-staged.log'},
 'flink_bounded':{'classification':'Feature materialization plus normalization and feedback groups of 3; exact same score recurrence. Every intermediate table and final output compared independently.','guard':json.loads((ROOT/'flink_bounded-guard.json').read_text()),'evidence':attempt('flink-bounded')},
 'timing':'Supplemental engines overlap canonical workload; canonical times are observed mixed-load times. performance.json is a separate test after all compatibility clients ended.'}
(ROOT/'client-setup-notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2));print('client notes written')
