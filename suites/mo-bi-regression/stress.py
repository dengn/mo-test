"""Bounded long-SQL replay; resource guards are failures, never engine crashes."""
import concurrent.futures,json,os,time
from pathlib import Path
import common as c
import run_sql

def identity(pid):
    root=Path('/proc')/str(pid)
    if root.joinpath('comm').read_text().strip()!='mo-service':raise RuntimeError('Guard PID is not mo-service')
    # PID reuse is detected from Linux starttime, not just the process name.
    return root.joinpath('stat').read_text().split(') ',1)[1].split()[19]

def rss(pid):
    for line in (Path('/proc')/str(pid)/'status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024
    return 0

def run(cases,state,args):
    token=identity(args.mo_pid) if args.mo_pid else None;records=[]
    for case in cases:
        # Separate connections and connection IDs for each owned query.
        with c.connection(state['schemas']['core'],timeout=max(120,case.get('timeout_s',20)+20)) as cx:
            cid=cx.thread_id();started=time.monotonic()
            def query():
                with cx.cursor() as q:q.execute(c.remap(case['sql'],state));return q.fetchall()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                job=pool.submit(query);guard=None
                while not job.done():
                    if args.mo_pid and identity(args.mo_pid)!=token:guard='service_identity_changed';break
                    if args.mo_pid and rss(args.mo_pid)>4096*1024**2:guard='rss_watchdog';break
                    if time.monotonic()-started>case.get('timeout_s',20):guard='wall_time_watchdog';break
                    time.sleep(.02)
                if guard:
                    # Only cancel the connection created for this query. Never
                    # restart/kill an externally provisioned MatrixOne service.
                    with c.connection(timeout=10) as control,control.cursor() as q:q.execute('KILL QUERY '+str(cid))
                try:
                    rows=job.result(timeout=15);result=c.record(case,rows)
                except Exception as exc:result={'id':case['id'],'status':'error','error':c.safe_error(exc)}
                if guard:result['status']=guard
                with cx.cursor() as q:q.execute('SELECT 1');result['same_connection_healthy']=q.fetchone()==(1,)
                result['elapsed_seconds']=round(time.monotonic()-started,6);records.append(result)
    return records
