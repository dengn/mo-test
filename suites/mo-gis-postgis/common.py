"""GIS differential harness. Raw failures are retained; geometry comparison is explicit."""
import collections
import concurrent.futures
import decimal
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

import psycopg
import pymysql
import shapely

P = Path(__file__).resolve().parent
DB = os.environ.get('GIS_MO_DATABASE', 'gis_functional_20261012')
MO_PORT = int(os.environ.get('GIS_MO_PORT', '6011'))
LOCAL = threading.local()


def connect(engine, timeout=40, database=True):
    if engine == 'mo':
        return pymysql.connect(host='127.0.0.1', port=MO_PORT, user='root', password='111',
            database=DB if database else None, autocommit=True, ssl_disabled=True,
            charset='utf8mb4', connect_timeout=5, read_timeout=timeout, write_timeout=timeout)
    c = psycopg.connect(host='127.0.0.1', port=65432, user='gis', password='gis_local_test',
                        dbname='gis', autocommit=True, connect_timeout=5)
    with c.cursor() as q:
        q.execute(f"SET statement_timeout='{timeout}s'")
        q.execute("SET search_path=gis_suite,public")
    return c


def query(c, sql, params=None):
    with c.cursor() as q:
        if params is None:
            q.execute(sql)
        else:
            q.execute(sql, params)
        return q.fetchall() if q.description else []


def error(e):
    return {'type': type(e).__name__, 'code': e.args[0] if e.args else None,
            'sqlstate': getattr(e, 'sqlstate', None), 'message': str(e)[:5000]}


def norm(v):
    if isinstance(v, (bytes, memoryview)):
        return {'hex': bytes(v).hex()}
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v


def number_equal(a, b, tol):
    if isinstance(a, (bool, int, float, decimal.Decimal)) and isinstance(b, (bool, int, float, decimal.Decimal)):
        if isinstance(a, float) or isinstance(b, float):
            if math.isnan(float(a)) and math.isnan(float(b)):
                return True
            return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
        return a == b
    return False


def equal(a, b, mode='scalar', tol=1e-8):
    if a is None or b is None:
        return a is b
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(equal(x, y, mode, tol) for x, y in zip(a, b))
    if number_equal(a, b, tol):
        return True
    if mode == 'typename':
        return str(a).upper().removeprefix('ST_') == str(b).upper().removeprefix('ST_')
    if mode == 'json':
        try:
            a = json.loads(a) if isinstance(a, str) else a
            b = json.loads(b) if isinstance(b, str) else b
            return a == b
        except Exception:
            return False
    if mode == 'hex':
        return str(a).lower() == str(b).lower()
    if mode == 'geometry':
        try:
            ga, gb = shapely.from_wkt(a), shapely.from_wkt(b)
            if ga.is_empty and gb.is_empty:
                return True
            if ga.equals(gb):
                return True
            return (ga.geom_type == gb.geom_type and
                    ga.hausdorff_distance(gb) <= tol and
                    math.isclose(ga.area, gb.area, rel_tol=tol, abs_tol=tol) and
                    math.isclose(ga.length, gb.length, rel_tol=tol, abs_tol=tol))
        except Exception:
            return False
    return a == b


def execute(engine, case):
    sql = case.get(engine + '_sql')
    if sql is None:
        return None, None
    if not hasattr(LOCAL, 'connections'):
        LOCAL.connections = {}
    if engine not in LOCAL.connections:
        LOCAL.connections[engine] = connect(engine)
    try:
        return query(LOCAL.connections[engine], sql), None
    except Exception as e:
        if getattr(e, 'args', ()) and e.args[0] in (2006, 2013, 0):
            LOCAL.connections.pop(engine, None)
        return None, error(e)


def run_case(case):
    t = time.monotonic()
    a, ae = execute('mo', case)
    b, be = execute('pg', case)
    status = 'pass'
    if case.get('expect') == 'reject_both':
        status = 'pass_expected_rejection' if ae and be else 'rejection_difference'
    elif case.get('expect') == 'mo_gap':
        status = 'verified_feature_gap' if ae and not be else 'feature_probe_review'
    elif case.get('expect') == 'mo_extension':
        status = 'pass_mo_extension' if not ae else 'mo_execution_error'
    elif ae or be:
        status = 'both_rejected' if ae and be else 'mo_execution_error' if ae else 'reference_rejected'
    elif case.get('comparison') == 'semantic_difference':
        status = 'documented_semantic_difference' if not equal(a, b, case.get('mode', 'scalar'), case.get('tol',1e-8)) else 'pass'
    elif not equal(a, b, case.get('mode','scalar'), case.get('tol',1e-8)):
        status = 'candidate_difference'
    if 'expected' in case and not ae:
        if not equal(a, case['expected'], case.get('mode','scalar'), case.get('oracle_tol',case.get('tol',1e-8))):
            status = 'independent_oracle_failure'
    return {'id': case['id'], 'category': case['category'], 'feature': case['feature'],
            'function': case.get('function'), 'status': status, 'seconds':time.monotonic()-t,
            'mo_rows':norm(a), 'pg_rows':norm(b), 'mo_error':ae, 'pg_error':be,
            'mode':case.get('mode','scalar'), 'comparison':case.get('comparison'),
            'notes':case.get('notes')}


def run_cases(cases, filename='results.jsonl', workers=8):
    output = P/filename
    complete = set()
    if output.exists():
        complete = {json.loads(l)['id'] for l in output.read_text().splitlines() if l}
    counts=collections.Counter();start=time.monotonic()
    pending=[c for c in cases if c['id'] not in complete]
    with output.open('a') as f, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for i, result in enumerate(ex.map(run_case,pending),1):
            f.write(json.dumps(result,default=str)+'\n');f.flush();counts[result['status']]+=1
            if i%200==0:
                print(json.dumps({'completed_new':i,'total':len(cases),'statuses':dict(counts),
                                  'elapsed':round(time.monotonic()-start,1)}),flush=True)
    print('DONE',len(pending),dict(counts),round(time.monotonic()-start,2),flush=True)


def save_cases(cases, name='cases.jsonl'):
    with (P/name).open('w') as f:
        for case in cases:
            f.write(json.dumps(case)+'\n')
