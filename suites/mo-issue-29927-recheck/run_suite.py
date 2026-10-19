"""Fresh databases, exact race trigger repetitions, and graceful owned restart."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from verify import connect,query,verify

SCRIPT_ROOT=Path(__file__).resolve().parent
P=Path(os.environ.get('ISSUE_OUTPUT_ROOT',str(SCRIPT_ROOT)))
BINARY=Path(os.environ.get('ISSUE_BINARY','/workspace/matrixone-29927-main/mo-service'))
EXPECTED=os.environ.get('ISSUE_EXPECTED_COMMIT','3e50e1b32d8da61bbbf70c89989fb08b671809de')
PORT=int(os.environ.get('ISSUE_MO_PORT','6014'))
RUNS=int(os.environ.get('ISSUE_RUNS','5'))
out={'expected_main_commit':EXPECTED,'runs':[],'service_restarts':[],'planned_max_runs':RUNS,'SQL_port':PORT}
def save():P.joinpath('summary.json').write_text(json.dumps(out,indent=2,default=str)+'\n')
def start(label):
    log=open(P/('server-'+label+'.log'),'a')
    proc=subprocess.Popen([str(BINARY),'-launch',str(P/'config/launch.toml')],cwd=BINARY.parent,
        env={**os.environ,'GOMAXPROCS':'4'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    P.joinpath('server.pid').write_text(str(proc.pid)+'\n')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if proc.poll() is not None:raise RuntimeError('Owned service exited '+str(proc.returncode))
        try:
            c=connect(port=PORT);version=query(c,'select git_version(),version()')[0];c.close()
            assert EXPECTED.startswith(version[0]),version
            out['runtime_version']=version;save();return proc
        except Exception:time.sleep(1)
    raise RuntimeError('SQL readiness deadline exceeded')
def stop(proc,label):
    # Only the process created by this runner is stopped, never a historical PID.
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:code=proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            out['service_restarts'].append({'label':label,'graceful_stop':False,'error':'SIGTERM did not finish within 60s'});save();raise
        out['service_restarts'].append({'label':label,'graceful_stop':True,'exit_code':code});save()

out['binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();save()
server=start('initial')
try:
    for i in range(1,RUNS+1):
        directory=P/'runs'/f'run-{i:02d}';directory.mkdir(parents=True,exist_ok=False)
        logfile=open(directory/'workload.log','w');t=time.monotonic()
        workload=subprocess.Popen([sys.executable,str(SCRIPT_ROOT/'workload_entry.py')],cwd=directory,
            stdout=logfile,stderr=subprocess.STDOUT)
        mode_samples=[];deadline=time.monotonic()+240
        while workload.poll() is None and time.monotonic()<deadline:
            try:
                c=connect(port=PORT,timeout=5)
                with c.cursor() as cur:
                    cur.execute('select * from mo_transactions() as t')
                    names=[x[0].lower() for x in cur.description]
                    indices=[n for n,name in enumerate(names) if name in ['mode','txn_mode','isolation','user_txn','user']]
                    rows=[{names[n]:row[n] for n in indices} for row in cur.fetchall()]
                c.close()
                if rows:mode_samples.append(rows)
            except Exception as e:mode_samples.append({'monitor_error':str(e)})
            time.sleep(1)
        if workload.poll() is None:
            workload.terminate();workload.wait(timeout=30)
            out['runs'].append({'run':i,'status':'timeout','seconds':time.monotonic()-t});save();break
        r={'run':i,'workload_exit_code':workload.returncode,'seconds':round(time.monotonic()-t,3),
            'transaction_mode_samples':mode_samples,'output_directory':str(directory.relative_to(P))}
        if workload.returncode!=0:r['status']='workload_error';out['runs'].append(r);save();break
        info=json.loads((directory/'run-metadata.json').read_text());r['database']=info['database']
        original=json.loads((directory/'index-race-output/index-race.json').read_text())
        r.update(acknowledged_writes=original['acknowledged_writes'],original_missing=original['missing'],
            original_corrupt=original['corrupt'],transient_client_errors=original['client_errors'],
            ddl_errors=[x for x in original['ddl_cases'] if x['error']])
        ledger=json.loads((directory/'index-race-output/index-race-ledger.json').read_text())
        checks=verify(r['database'],ledger,'post_load',directory,port=PORT)
        r['post_load_check_count']=len(checks['checks']);r['post_load_errors']=checks['errors']
        r['original_POST_LOAD_errors']=re.findall(r'^POST_LOAD.*(?:no such table|missing visibility metadata|ERROR|internal error).*$',(directory/'workload.log').read_text(),re.M)
        r['status']='pass' if not checks['errors'] and not r['original_missing'] and not r['original_corrupt'] and not r['original_POST_LOAD_errors'] else 'persistent_failure'
        out['runs'].append(r);save();print('RUN',i,r['status'],'acked',r['acknowledged_writes'],'DDL errors',len(r['ddl_errors']),flush=True)
        if r['status']!='pass' and os.environ.get('ISSUE_STOP_ON_FAILURE')=='1':break
    stop(server,'before_restart');server=None
    server=start('restarted')
    for r in out['runs']:
        if 'database' not in r:continue
        directory=P/r['output_directory'];ledger=json.loads((directory/'index-race-output/index-race-ledger.json').read_text())
        checks=verify(r['database'],ledger,'post_restart',directory,port=PORT)
        r['post_restart_check_count']=len(checks['checks']);r['post_restart_errors']=checks['errors']
        if checks['errors']:r['status']='persistent_failure'
        save();print('RESTART',r['run'],'errors',len(checks['errors']),flush=True)
    out['total_acknowledged_writes']=sum(r.get('acknowledged_writes',0) for r in out['runs'])
    out['panic_log_matches']={f.name:len(re.findall(r'panic:|fatal error:|DATA RACE',f.read_text())) for f in P.glob('server-*.log')}
    out['all_runs_passed']=len(out['runs'])==RUNS and all(r['status']=='pass' for r in out['runs'])
    out['finished_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
finally:
    if server is not None:stop(server,'final_stop')
assert out.get('all_runs_passed'),out
