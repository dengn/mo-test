"""Every final catalog pointer resolved to a real byte-exact archived case; originals retained."""
import json,gzip,hashlib,zipfile,collections,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import ROOT
NAME='mo-analysis-needs-lab';repo=Path('/workspace/mo-test')
def main():
 manifest=json.loads((repo/'archives/manifest.json').read_text());suite=next(s for s in manifest['suites'] if s['name']==NAME);archive=ROOT/suite['archive_name'];catalog={}
 with gzip.open(repo/suite['catalog'],'rt') as f:
  for line in f:
   row=json.loads(line);assert row['case_id'] not in catalog;catalog[row['case_id']]=row
 expected_by_member=collections.defaultdict(dict)
 for row in catalog.values():expected_by_member[row['member']][row['line']]=row
 resolved=set();statuses=collections.Counter();initial_count=0;retest_count=0
 with zipfile.ZipFile(archive) as z:
  for member in suite['canonical_members']:
   wanted=expected_by_member[member]
   with z.open(member) as f:
    for lineno,line in enumerate(f,1):
     r=json.loads(line)
     if '/main-001/' in member:initial_count+=1
     else:retest_count+=1
     if lineno not in wanted:continue
     row=wanted[lineno];assert r['case_id']==row['case_id'] and r['status']==row['status'];assert r['domain']==row['family'];assert r['parameters']['parameter']==row['parameter'];assert row['case_id'] not in resolved;resolved.add(row['case_id']);statuses[r['status']]+=1
     if r['status']=='pass':assert r['input']['full_values_compared'] and r['output']['full_values_compared']
  assert resolved==set(range(100000));assert initial_count==100000;assert dict(statuses)==suite['canonical_statuses']
  # Original artifact inventory is validated against bytes inside the archive.
  for r in json.loads(z.read(NAME+'/artifact-manifest.json')):
   b=z.read(NAME+'/'+r['path']);assert len(b)==r['bytes'];assert hashlib.sha256(b).hexdigest()==r['sha256'],r['path']
 result=dict(final_unique_cases=len(resolved),statuses=dict(statuses),initial_records=initial_count,repair_retest_records=retest_count,every_catalog_pointer_resolved=True,artifact_sha256_verified=True);(ROOT/'package-verification.json').write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':main()
