"""Verify this suite's files and coverage claims without restoring historical archives."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'artifact-manifest.json').read_text())
    for entry in manifest['files']:
        path = ROOT / entry['path']
        data = path.read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise RuntimeError('Artifact changed: ' + entry['path'])
    workflow = manifest['workflow']
    data = (ROOT.parent.parent / workflow['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == workflow['sha256'], workflow['path']
    inventory = json.loads((ROOT / 'inventory.json').read_text())
    catalog = json.loads((ROOT / 'catalog/projects-1000.json').read_text())
    cases = [json.loads(p.read_text()) for p in (ROOT / 'cases').glob('*.json')]
    implemented = [app for app in inventory['applications'] if app['independent_native_driver'] == 'implemented']
    assert len(implemented) == inventory['independent_native_driver_count'] == 20
    assert len(cases) == inventory['SQL_case_count'] == 20
    assert len({case['id'] for case in cases}) == len(cases)
    assert sum(bool(case.get('panic')) for case in cases) == 4
    assert len(catalog) == 1000
    assert len({app['repo'] for app in catalog}) == 1000
    assert len(inventory['applications']) == 61
    assert inventory['historical_basic_business_pass_count'] == 58
    assert sum(app['runtime_status'].startswith('smoke_passed') for app in inventory['applications']) == 58
    print(f"PASS: {len(manifest['files'])} artifact hashes; 20 independent native drivers; 20 SQL fixtures; 1000 candidates.")


if __name__ == '__main__':
    main()
