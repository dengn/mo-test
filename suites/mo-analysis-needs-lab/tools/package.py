"""Complete frozen bundle, original main index, and byte-exact browseable provenance."""
import sys,json,hashlib,gzip,zipfile,shutil,collections,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import ROOT
from scenarios import DOMAINS
REPO=Path('/workspace/mo-test');NAME='mo-analysis-needs-lab';PREFIX=NAME+'/'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def selected(p):
 rel=p.relative_to(ROOT);s=str(rel)
 return p.is_file() and '__pycache__' not in rel.parts and not s.startswith('package-') and p.suffix not in ['.pyc','.zip'] and not '.git' in rel.parts

def main():
 report=json.loads((ROOT/'report.json').read_text());assert report['canonical_cases']==100000
 archive=ROOT/'matrixone-analysis-needs-100000.zip';assert not archive.exists()
 files=sorted(p for p in ROOT.rglob('*') if selected(p))
 manifest=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in files];(ROOT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2));files.append(ROOT/'artifact-manifest.json')
 with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p in files:z.write(p,PREFIX+str(p.relative_to(ROOT)))
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None;entries=len(z.infolist());uncompressed=sum(i.file_size for i in z.infolist())
 target=REPO/'suites'/NAME;target.mkdir(exist_ok=False);provenance=[]
 for p in files:
  rel=p.relative_to(ROOT)
  # Browse code, fixtures, summaries/diagnostic controls and report. Full case JSONL and state artifacts remain in byte-exact archive.
  browse=(rel.parts[0] not in ['results','inputs','attempts','frozen-main'] and p.suffix in ['.py','.md','.txt','.json','.png','.html','.sql']) or rel.parts[0]=='inputs' or (rel.parts[0]=='results' and p.name in ['summary.json','run-config.json','checkpoint-journal.json','health-before.json','health-after.json','continuation.json','continuation-corrected.json'])
  if browse:
   dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);provenance.append(dict(path=str(dst.relative_to(REPO)),zip_member=PREFIX+str(rel),bytes=p.stat().st_size,sha256=sha(p)))
 members=[PREFIX+f'results/main-001/{d}.jsonl' for d in DOMAINS]+[PREFIX+'results/retest/cases.jsonl'];retests={}
 for line_number,line in enumerate((ROOT/'results/retest/cases.jsonl').open(),1):
  r=json.loads(line);assert r['case_id'] not in retests;retests[r['case_id']]=(r,line_number)
 catalog=REPO/'catalog'/f'{NAME}.jsonl.gz';counts=collections.Counter();ids=set()
 with gzip.GzipFile(filename=str(catalog),mode='wb',mtime=0) as f:
  for d,member in zip(DOMAINS,members):
   for lineno,line in enumerate((ROOT/f'results/main-001/{d}.jsonl').open(),1):
    r=json.loads(line);ident=r['case_id'];source_member=member;source_line=lineno
    if ident in retests:
     repaired,repaired_line=retests[ident];assert r['status']!='pass' and repaired['sql']==r['sql'] and repaired['parameters']==r['parameters'];r=repaired;source_member=PREFIX+'results/retest/cases.jsonl';source_line=repaired_line
    assert ident not in ids;ids.add(ident);counts[r['status']]+=1;row=dict(suite=NAME,case_id=ident,status=r['status'],client=r['client'],family=d,scenario=r['workflow'],template=r['template'],parameter=r['parameters']['parameter'],member=source_member,line=source_line);f.write((json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode())
 assert ids==set(range(100000));parts=[];partdir=REPO/'archives'/NAME;partdir.mkdir(exist_ok=False)
 with archive.open('rb') as f:
  k=0
  while block:=f.read(40*1024**2):
   path=partdir/(archive.name+f'.part{k:03}');path.write_bytes(block);parts.append(dict(path=str(path.relative_to(REPO)),bytes=len(block),sha256=hashlib.sha256(block).hexdigest()));k+=1
 suite=dict(name=NAME,archive_name=archive.name,archive_bytes=archive.stat().st_size,archive_sha256=sha(archive),zip_prefix=PREFIX,zip_entries=entries,uncompressed_bytes=uncompressed,canonical_cases=100000,canonical_statuses=dict(counts),canonical_members=members,catalog=str(catalog.relative_to(REPO)),catalog_sha256=sha(catalog),parts=parts)
 path=REPO/'archives/manifest.json';archives=json.loads(path.read_text());assert NAME not in [s['name'] for s in archives['suites']];archives['suites'].append(suite);path.write_text(json.dumps(archives,indent=2))
 path=REPO/'catalog/summary.json';summary=json.loads(path.read_text());summary['canonical_cases']+=100000;summary['canonical_passed']+=counts['pass'];summary['canonical_nonpass']+=100000-counts['pass'];summary['suites'].append({k:suite[k] for k in ['name','canonical_cases','canonical_statuses','canonical_members','catalog']});path.write_text(json.dumps(summary,indent=2))
 path=REPO/'catalog/source-files.json';sources=json.loads(path.read_text());sources+=provenance;path.write_text(json.dumps(sources,indent=2))
 print(json.dumps(dict(suite=suite,browseable_files=len(provenance),total_cases=summary['canonical_cases']),indent=2))
if __name__=='__main__':main()
