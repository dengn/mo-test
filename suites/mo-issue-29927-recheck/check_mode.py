"""Supplementary transaction-mode inspection; startup uses owned preserved data."""
from pathlib import Path
import json
import os
import signal
import subprocess
import time
from verify import connect,query
P=Path(__file__).resolve().parent
results=[]
for name,port,binary in [('old-control',6015,'/workspace/matrixone-latest/mo-service'),('main',6014,'/workspace/matrixone-29927-main/mo-service')]:
    directory=P/'old-control' if name=='old-control' else P
    log=open(directory/'server-mode-check.log','w')
    proc=subprocess.Popen([binary,'-launch',str(directory/'config/launch.toml')],cwd=Path(binary).parent,
        env={**os.environ,'GOMAXPROCS':'4'},stdout=log,stderr=subprocess.STDOUT)
    c=None
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:c=connect(port=port);break
            except Exception:time.sleep(1)
        assert c is not None
        query(c,'begin')
        query(c,'select count(*) from mo_catalog.mo_tables')
        with c.cursor() as cur:
            cur.execute('select * from mo_transactions() as t')
            columns=[x[0] for x in cur.description];rows=cur.fetchall()
            obj=[dict(zip(columns,row)) for row in rows]
        query(c,'rollback')
        entry={'service':name,'port':port,'version':query(c,'select git_version()')[0][0],'columns':columns,'transactions':obj}
        assert any(str(v.get('txn_mode','')).lower()=='pessimistic' for v in obj),entry
        results.append(entry)
    finally:
        if c:c.close()
        if proc.poll() is None:proc.send_signal(signal.SIGTERM);proc.wait(timeout=60)
    print(name,'transaction mode verified',flush=True)
(P/'transaction-mode-verification.json').write_text(json.dumps(results,indent=2,default=str)+'\n')
