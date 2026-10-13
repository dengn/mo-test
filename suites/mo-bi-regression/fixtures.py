"""Generate and load only run-owned schemas; independently verify every input."""
import csv,hashlib,io,json,uuid
from pathlib import Path
import common as c
import fixture_core as core
import fixture_baseline as baseline
import fixture_extra as extra

def stored_rows(ddl,rows):
    columns=ddl.split(', ')
    scales=[__import__('re').search(r'DECIMAL\(\d+,(\d+)\)',col) for col in columns]
    return [tuple(v.quantize(c.D(1).scaleb(-int(m[1])),rounding=c.decimal.ROUND_HALF_UP)
                  if v is not None and m else v for v,m in zip(row,scales)) for row in rows]

def csv_hashes(data):
    hashes={}
    for table,rows in data.items():
        out=io.StringIO(newline='');w=csv.writer(out);w.writerow(core.COLNAMES[table])
        w.writerows([['\\N' if v is None else str(v) for v in row] for row in rows])
        hashes[table]=hashlib.sha256(out.getvalue().encode()).hexdigest()
    return hashes

def verify_generated(data):
    counts={k:len(v) for k,v in data.items()}
    if counts!=c.MANIFEST['fixture_rows']:raise RuntimeError('Fixture row-count drift')
    if csv_hashes(data)!=c.MANIFEST['fixture_csv_sha256']:raise RuntimeError('Deterministic fixture hash drift')
    return counts

def load_tables(q,db,schema,data):
    q.execute('USE '+c.identifier(db));audit={}
    for table,ddl in schema.items():
        q.execute('CREATE TABLE '+c.identifier(table)+' ('+ddl+')')
        rows=data[table];size=len(rows[0]) if rows else len(ddl.split(', '))
        insert='INSERT INTO '+c.identifier(table)+' VALUES ('+','.join(['%s']*size)+')'
        for i in range(0,len(rows),1000):q.executemany(insert,rows[i:i+1000])
        q.execute('SELECT * FROM '+c.identifier(table));actual=c.canon(q.fetchall());expected=c.canon(stored_rows(ddl,rows))
        key=lambda r:json.dumps(r,ensure_ascii=False)
        actual.sort(key=key);expected.sort(key=key)
        if actual!=expected:raise RuntimeError('Fixture values differ: '+table)
        audit[table]={'rows':len(rows),'all_fields_sha256':c.digest(expected)}
    return audit

def create(out,target):
    run_id=uuid.uuid4().hex[:16];prefix='mo_bi_'+run_id
    state={'run_id':run_id,'target':target,'schemas':{k:prefix+'_'+k for k in ['core','baseline','semantic','extra']},'owned_schemas':[],'audits':{}}
    # Record ownership immediately, including failures, so cleanup never guesses by prefix.
    path=Path(out)/'fixture-state.json'
    data,_=core.fixtures();verify_generated(data)
    with c.connection(timeout=180) as cx,cx.cursor() as q:
        for key,db in state['schemas'].items():
            q.execute('CREATE DATABASE '+c.identifier(db));state['owned_schemas'].append(db);c.write_json(path,state)
            if key=='core':state['audits'][key]=load_tables(q,db,core.SCHEMA,data)
            if key=='baseline':state['audits'][key]=load_tables(q,db,baseline.SCHEMA,baseline.data())
            if key=='extra':state['audits'][key]=load_tables(q,db,extra.SMALL_SCHEMA,extra.SMALL_DATA)
        for name,model in json.loads((c.ROOT/'corpus/models.json').read_text()).items():
            q.execute('CREATE VIEW '+c.identifier(state['schemas']['semantic'])+'.'+c.identifier(name)+' AS '+c.remap(model['sql'],state))
        state['audits']['semantic']={'views':24}
    c.write_json(path,state);return state

def reuse(path,target):
    state=json.loads(Path(path).read_text())
    if state['target']['target_identity']!=target['target_identity']:raise RuntimeError('Fixture belongs to another target')
    prefix='mo_bi_'+state['run_id']+'_'
    if len(state['run_id'])!=16 or any(not db.startswith(prefix) for db in state['owned_schemas']):raise RuntimeError('Invalid fixture ownership record')
    # Row counts alone would miss changed monetary or dimension values.
    data,_=core.fixtures();datasets={'core':(core.SCHEMA,data),'baseline':(baseline.SCHEMA,baseline.data()),'extra':(extra.SMALL_SCHEMA,extra.SMALL_DATA)}
    with c.connection() as cx,cx.cursor() as q:
        for key,(schema,data) in datasets.items():
            for table,rows in data.items():
                q.execute('SELECT * FROM '+c.identifier(state['schemas'][key])+'.'+c.identifier(table))
                actual=c.canon(q.fetchall());expected=c.canon(stored_rows(schema[table],rows));sort=lambda row:json.dumps(row,ensure_ascii=False)
                if sorted(actual,key=sort)!=sorted(expected,key=sort):raise RuntimeError('Reused fixture drift: '+table)
    return state

def cleanup(state):
    prefix='mo_bi_'+state['run_id']+'_'
    with c.connection() as cx,cx.cursor() as q:
        for db in reversed(state['owned_schemas']):
            if not db.startswith(prefix):raise RuntimeError('Refusing cleanup without ownership')
            q.execute('DROP DATABASE '+c.identifier(db))
