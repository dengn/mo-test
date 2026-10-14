"""Verify portable suite hashes and the completeness of frozen run evidence."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    manifest=json.loads((ROOT/'artifact-manifest.json').read_text())
    for entry in manifest['files']:
        path=ROOT/entry['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise RuntimeError('Artifact changed: '+entry['path'])
    catalog=json.loads((ROOT/'projects.json').read_text())
    assert len({p['id'] for p in catalog['projects']})==22
    report=json.loads((ROOT/'evidence/validation-report.json').read_text())
    entries={g['group']:g for g in report['groups']}
    for group in catalog['groups']:
        entry=entries[group]
        expected={name for p in catalog['projects'] if p['group']==group for name in p['gate_tests']}
        assert entry['status']=='PASS' and entry['test_exit_code']==entry['cleanup_exit_code']==0
        assert not entry['missing'] and not entry['problems']
        assert set(entry['passed'])==expected
        assert entry['requirements_sha256']==hashlib.sha256((ROOT/catalog['groups'][group]['requirements']).read_bytes()).hexdigest()
    assert sum(len(g['passed']) for g in entries.values())==33
    print(json.dumps(dict(status='PASS',projects=22,groups=11,required_tests=33,files_checked=len(manifest['files']))))
if __name__=='__main__':main()
