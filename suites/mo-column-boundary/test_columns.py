#!/usr/bin/env python3
"""Sequential physical-column probes; raw SQL, timings and independent row oracle.

Requires PyMySQL. Defaults target the existing isolated local stress service.
Never changes server settings or stops the service. Cancellation is scoped to
this probe's connection. Timeout/resource cancellation is not a column limit.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import pymysql

P = Path(__file__).resolve().parent
LOG = Path('/workspace/mo-stress/server.log')
CG = Path('/sys/fs/cgroup')
STOP = threading.Event()
ACTIVE = {'connection_id': None, 'stage': None, 'started': 0, 'timeout': 300}
GUARD_EVENTS = []
ARGS = None


def conn(db=None, timeout=330):
    return pymysql.connect(host='127.0.0.1', port=6001, user='root',
                           password='111', database=db, autocommit=True,
                           connect_timeout=5, read_timeout=timeout,
                           write_timeout=timeout, ssl_disabled=True,
                           charset='utf8mb4')


def err(e):
    return {'type': type(e).__name__, 'code': e.args[0] if e.args else None,
            'message': str(e)[:4000]}


def snapshot():
    x = {'unix_time': time.time()}
    for name in ('memory.current', 'memory.peak', 'memory.events', 'cpu.stat'):
        try:
            x[name] = (CG / name).read_text().strip()
        except OSError:
            pass
    try:
        stat = dict(line.split() for line in (CG / 'memory.stat').read_text().splitlines())
        x['memory_anon_kernel_bytes'] = int(stat['anon']) + int(stat['kernel'])
    except (OSError, KeyError, ValueError):
        pass
    try:
        pid = int(Path('/workspace/mo-stress/server.pid').read_text())
        x['pid'] = pid
        status = Path(f'/proc/{pid}/status').read_text()
        x.update({line.split(':')[0]: line.split(':', 1)[1].strip()
                  for line in status.splitlines()
                  if line.startswith(('VmRSS:', 'VmHWM:', 'Threads:', 'State:'))})
    except (OSError, ValueError):
        x['process_unavailable'] = True
    return x


def monitor():
    seen = set()
    with (P / 'resources.jsonl').open('a') as out:
        while not STOP.is_set():
            x = snapshot()
            x['active'] = dict(ACTIVE)
            out.write(json.dumps(x) + '\n')
            out.flush()
            aid = ACTIVE['connection_id']
            age = time.monotonic() - ACTIVE['started'] if aid else 0
            # Existing uploaded result archives occupy reclaimable file cache.
            # Guard non-file memory rather than mistaking that cache for OOM.
            mem = int(x.get('memory_anon_kernel_bytes', x.get('memory.current', '0')))
            reason = ('memory_guard_28GiB' if mem > 28 * 1024**3 else
                      'stage_deadline' if aid and age > ACTIVE['timeout'] else None)
            key = (aid, ACTIVE['started'])
            if reason and aid and key not in seen:
                seen.add(key)
                event = {'reason': reason, 'stage': ACTIVE['stage'],
                         'connection_id': aid, 'elapsed': age, 'memory_bytes': mem}
                try:
                    control = conn(timeout=5)
                    with control.cursor() as q:
                        q.execute(f'KILL QUERY {int(aid)}')
                    control.close()
                    event['cancel'] = 'sent'
                except Exception as e:
                    event['cancel_error'] = err(e)
                GUARD_EVENTS.append(event)
                print('GUARD', json.dumps(event), flush=True)
            STOP.wait(0.5)


def run_step(c, label, sql, oracle=None):
    sql_bytes = sql.encode()
    rec = {'stage': label, 'sql_bytes': len(sql_bytes),
           'sql_sha256': hashlib.sha256(sql_bytes).hexdigest(),
           'before': snapshot()}
    path = P / 'sql' / (label + '.sql.gz')
    path.parent.mkdir(exist_ok=True)
    with gzip.GzipFile(filename=str(path), mode='wb', mtime=0) as f:
        f.write(sql_bytes)
    rec['sql_file'] = str(path.relative_to(P))
    before_events = len(GUARD_EVENTS)
    ACTIVE.update(connection_id=c.thread_id(), stage=label,
                  started=time.monotonic(), timeout=ARGS.deadline)
    t = time.monotonic()
    print('START', label, len(sql_bytes), flush=True)
    try:
        with c.cursor() as q:
            q.execute(sql)
            rows = q.fetchall() if q.description else ()
            rec['affected_rows'] = q.rowcount
            rec['result_rows'] = len(rows)
            rec['result_columns'] = len(q.description or ())
            if len(rows) <= 8 and rec['result_columns'] <= 16:
                rec['rows'] = rows
            if oracle:
                oracle(rows, q.description)
                rec['oracle'] = 'pass'
            rec['status'] = 'success'
    except Exception as e:
        rec['status'] = 'error'
        rec['error'] = err(e)
    rec['seconds'] = time.monotonic() - t
    ACTIVE.update(connection_id=None, stage=None)
    rec['guard_events'] = GUARD_EVENTS[before_events:]
    rec['after'] = snapshot()
    print('END', label, rec['status'], round(rec['seconds'], 3),
          rec.get('error', ''), flush=True)
    with (P / 'steps.jsonl').open('a') as f:
        f.write(json.dumps(rec, default=str) + '\n')
    return rec


def check(value):
    def oracle(rows, _):
        assert tuple(tuple(r) for r in rows) == value, (rows[:3], value)
    return oracle


def columns(n):
    return [f'c{i:07d}' for i in range(1, n + 1)]


def test_size(n):
    suffix = '_nopk' if ARGS.no_primary_key else ''
    name = f'wide_{n}' + suffix
    prefix = str(n) + suffix
    names = columns(n)
    c = conn(ARGS.database, ARGS.deadline + 30)
    steps = []
    # Isolated per-run database means no fixture collisions or silent replacement.
    defs = [col + ' int' + (' primary key' if i == 0 and not ARGS.no_primary_key else '')
            for i, col in enumerate(names)]
    s = run_step(c, f'{prefix}_create', f'create table {name}(' + ','.join(defs) + ')')
    steps.append(s)
    if s['status'] == 'success':
        steps.append(run_step(c, f'{prefix}_metadata_count',
                             "select count(*) from information_schema.columns "
                             f"where table_schema='{ARGS.database}' and table_name='{name}'",
                             check(((n,),))))
        values = ','.join(str(i) for i in range(1, n + 1))
        s = run_step(c, f'{prefix}_insert_all', f'insert into {name} values({values})')
        steps.append(s)
        if s['status'] == 'success':
            ids = sorted(set((1, max(1, n // 2), n)))
            projection = ','.join(names[i-1] for i in ids)
            steps.append(run_step(c, f'{prefix}_select_edges',
                                 f'select {projection} from {name}',
                                 check((tuple(ids),))))
            def full_oracle(rows, description):
                assert len(description) == n, (len(description), n)
                assert len(rows) == 1, len(rows)
                assert tuple(rows[0]) == tuple(range(1, n + 1)), 'wide row mismatch'
                assert [d[0] for d in description] == names, 'column order/name mismatch'
            steps.append(run_step(c, f'{prefix}_select_star',
                                 f'select * from {name}', full_oracle))
            steps.append(run_step(c, f'{prefix}_update_tail',
                                 f'update {name} set {names[-1]}=-{n} where {names[0]}=1'))
            steps.append(run_step(c, f'{prefix}_verify_update',
                                 f'select {names[-1]} from {name} where {names[0]}=1',
                                 check(((-n,),))))
            steps.append(run_step(c, f'{prefix}_restore_tail',
                                 f'update {name} set {names[-1]}={n} where {names[0]}=1'))
    try:
        c.close()
    except Exception:
        pass
    health = {}
    try:
        c = conn(timeout=10)
        with c.cursor() as q:
            q.execute('select 1')
            health['select_1'] = q.fetchall()
            q.execute("select count(*) from information_schema.tables "
                      f"where table_schema='{ARGS.database}' and table_name='{name}'")
            health['table_exists'] = q.fetchall()
        c.close()
        health['status'] = 'healthy'
    except Exception as e:
        health = {'status': 'error', 'error': err(e)}
    record = {'columns': n, 'table': name, 'primary_key': not ARGS.no_primary_key,
              'steps': steps, 'health': health}
    with (P / 'results.jsonl').open('a') as f:
        f.write(json.dumps(record, default=str) + '\n')
    return health['status'] == 'healthy'


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument('--sizes', type=int, nargs='+', default=[1000, 10000, 100000])
    ap.add_argument('--database', default='column_boundary_' + str(int(time.time())))
    ap.add_argument('--deadline', type=int, default=300)
    ap.add_argument('--no-primary-key', action='store_true')
    ARGS = ap.parse_args()
    P.mkdir(exist_ok=True)
    existing = P / 'environment.json'
    c = conn()
    with c.cursor() as q:
        q.execute('select version(),@@max_allowed_packet')
        environment = {'server': q.fetchall(), 'database': ARGS.database,
                       'deadline_seconds': ARGS.deadline, 'pid_before': snapshot(),
                       'server_log_offset': LOG.stat().st_size,
                       'client_version': pymysql.__version__, 'argv': vars(ARGS)}
        q.execute(f'create database if not exists {ARGS.database}')
    c.close()
    if not existing.exists():
        existing.write_text(json.dumps(environment, default=str, indent=2))
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        for n in ARGS.sizes:
            if not test_size(n):
                print('STOP: service health failed; no larger probe submitted', flush=True)
                break
    finally:
        STOP.set()
        thread.join(8)
        (P / 'last-state.json').write_text(json.dumps(snapshot(), indent=2))
        (P / 'guard-events.json').write_text(json.dumps(GUARD_EVENTS, indent=2))


if __name__ == '__main__':
    main()
