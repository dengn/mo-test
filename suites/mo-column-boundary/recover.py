#!/usr/bin/env python3
"""Archive crash evidence and restart ONLY an already exited stress service."""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import time
import test_columns as probe

ap = argparse.ArgumentParser()
ap.add_argument('tag')
args = ap.parse_args()
pid = int(Path('/workspace/mo-stress/server.pid').read_text())
try:
    status = Path(f'/proc/{pid}/status').read_text()
    if not any(line.startswith('State:') and 'Z' in line for line in status.splitlines()):
        raise SystemExit('Refusing to restart a live service; inspect it first.')
except FileNotFoundError:
    pass
log = probe.LOG.read_bytes()
with gzip.GzipFile(filename=str(probe.P / f'server-before-{args.tag}.log.gz'),
                   mode='wb', mtime=0) as f:
    f.write(log)
idx = log.find(b'panic:')
(probe.P / f'panic-{args.tag}.log').write_bytes(log[idx:] if idx >= 0 else b'')
subprocess.run(['bash', '/workspace/mo-stress/start.sh'], check=True)
start = time.monotonic()
while time.monotonic() - start < 120:
    try:
        c = probe.conn(timeout=120)
        records = {}
        with c.cursor() as q:
            q.execute('select 1')
            records['health'] = q.fetchall()
            for n in (1000, 10000, 65532):
                q.execute('select count(*) from information_schema.tables '
                          f"where table_schema='column_boundary_20261012' and table_name='wide_{n}'")
                exists = q.fetchone()[0]
                if exists:
                    q.execute(f'select * from column_boundary_20261012.wide_{n}')
                    rows = q.fetchall()
                    ok = len(rows) == 1 and tuple(rows[0]) == tuple(range(1, n + 1))
                    records[str(n)] = {'rows': len(rows), 'columns': len(q.description),
                                       'all_values_match': ok}
                    if len(rows) == 1:
                        mismatches = [(i, v) for i, v in enumerate(rows[0], 1) if i != v]
                        records[str(n)]['mismatch_count'] = len(mismatches)
                        records[str(n)]['mismatch_samples'] = mismatches[:16]
        c.close()
        records.update(pid_before=pid, pid_after=int(Path('/workspace/mo-stress/server.pid').read_text()),
                       recovery_check_seconds=time.monotonic()-start)
        (probe.P / f'recovery-{args.tag}.json').write_text(json.dumps(records, indent=2))
        print(json.dumps(records), flush=True)
        break
    except Exception as e:
        last = repr(e)
        time.sleep(1)
else:
    (probe.P / f'recovery-{args.tag}.json').write_text(json.dumps({'error': last}))
    raise SystemExit(last)
