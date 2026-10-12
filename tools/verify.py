#!/usr/bin/env python3
"""Check source provenance, every canonical index and every original bundle."""
import collections
import gzip
import hashlib
import json
from restore import ROOT, restore

def main():
    sources = json.loads((ROOT / 'catalog/source-files.json').read_text())
    for entry in sources:
        data = (ROOT / entry['path']).read_bytes()
        assert len(data) == entry['bytes'], entry['path']
        assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
    research_count = 0
    for research_manifest in (ROOT / 'research').glob('*/artifact-manifest.json'):
        for entry in json.loads(research_manifest.read_text()):
            data = (research_manifest.parent / entry['path']).read_bytes()
            assert len(data) == entry['bytes'], entry['path']
            assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
            research_count += 1
    manifest = json.loads((ROOT / 'archives/manifest.json').read_text())
    total = 0
    for suite in manifest['suites']:
        assert hashlib.sha256((ROOT / suite['catalog']).read_bytes()).hexdigest() == suite['catalog_sha256'], suite['catalog']
        ids = set()
        statuses = collections.Counter()
        with gzip.open(ROOT / suite['catalog'], 'rt') as source:
            for line in source:
                row = json.loads(line)
                assert row['suite'] == suite['name']
                assert row['member'] in suite['canonical_members']
                assert isinstance(row['case_id'], int) and row['case_id'] not in ids
                ids.add(row['case_id'])
                statuses[row['status']] += 1
        assert ids == set(range(suite['canonical_cases'])), suite['name']
        assert dict(statuses) == suite['canonical_statuses'], suite['name']
        total += len(ids)
        restore(suite, ROOT / 'work', verify_only=True)
    summary = json.loads((ROOT / 'catalog/summary.json').read_text())
    assert total == summary['canonical_cases'] == sum(s['canonical_cases'] for s in manifest['suites'])
    assert summary['canonical_passed'] + summary['canonical_nonpass'] == total
    print(f'PASS: {len(sources)} byte-exact source/report files; {research_count} research files; {total} unique canonical cases; all archive hashes and CRCs.')

if __name__ == '__main__':
    main()
