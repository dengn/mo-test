"""Verify imported independent references and reproducible synthetic inputs."""
import gzip,hashlib,json
from pathlib import Path
import common as c
import fixtures,fixture_core

def verify():
    counts={}
    for name,entry in c.MANIFEST['packs'].items():
        path=c.ROOT/'corpus'/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Corpus hash mismatch: '+name)
        ids=set();count=0
        for case in c.corpus(name.removesuffix('.jsonl.gz')):
            if case['id'] in ids:raise RuntimeError('Duplicate case ID: '+case['id'])
            if case.get('expected') is None:raise RuntimeError('Missing independent expected result')
            ids.add(case['id']);count+=1
        if count!=entry['count']:raise RuntimeError('Corpus count mismatch: '+name)
        counts[name]=count
    path=c.ROOT/'corpus/known-client-values.json.gz'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=c.MANIFEST['known_client_values']['sha256']:raise RuntimeError('Known-client diagnostic drift')
    models=json.loads((c.ROOT/'corpus/models.json').read_text())
    if len(models)!=24 or len({v['id'] for v in models.values()})!=24:raise RuntimeError('Semantic model mapping drift')
    data,_=fixture_core.fixtures();rows=sum(fixtures.verify_generated(data).values())
    manifest=c.ROOT/'artifact-manifest.json'
    if manifest.exists():
        frozen=json.loads(manifest.read_text())
        for entry in frozen['files']:
            p=c.ROOT/entry['path'];blob=p.read_bytes()
            if len(blob)!=entry['bytes'] or hashlib.sha256(blob).hexdigest()!=entry['sha256']:raise RuntimeError('Portable artifact drift: '+entry['path'])
        workflow=frozen.get('workflow')
        if workflow and hashlib.sha256((c.ROOT.parent.parent/workflow['path']).read_bytes()).hexdigest()!=workflow['sha256']:raise RuntimeError('Regression workflow drift')
    return {'corpora':counts,'generated_fixture_rows':rows,'models':24}

if __name__=='__main__':print(json.dumps(verify(),indent=2))
