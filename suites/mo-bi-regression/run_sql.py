"""SQL replay with exact references and narrow known-error classification."""
import concurrent.futures,json,os,re,threading,time
from collections import Counter
import common as c

LOCAL=threading.local()
CONNECTIONS=[]
LOCK=threading.Lock()
KNOWN='non-equality correlated aggregate with outer composition cannot be safely decorrelated is not yet implemented'

def selected(profile):
    if profile=='smoke':
        # One micro and dense case per supported analytical template, plus every
        # shared BI analytical pattern; unsupported template remains in full sql.
        return [r for r in c.corpus('analytics') if r['scenario_id'] in (101,191) and r['template_id']!='D03T09']+list(c.corpus('sql-projection'))
    if profile=='sql':return list(c.corpus('analytics'))+list(c.corpus('sql-projection'))
    if profile=='extreme':return list(c.corpus('extreme'))
    raise ValueError(profile)

def run_one(case,state,mode):
    started=time.monotonic();database=state['schemas']['core'] if case['id'].startswith(('M20-','XSQL-')) else state['schemas']['baseline']
    try:
        key=database
        if not hasattr(LOCAL,'connections'):LOCAL.connections={}
        if key not in LOCAL.connections:
            cx=c.connection(database,timeout=max(120,case.get('timeout_s',0)+10));LOCAL.connections[key]=cx
            with LOCK:CONNECTIONS.append(cx)
        cx=LOCAL.connections[key]
        with cx.cursor() as q:
            q.execute(c.remap(case['sql'],state));rows=q.fetchall()
            result=c.record(case,rows)
            q.execute('SELECT 1');result['same_connection_healthy']=q.fetchone()==(1,)
    except Exception as exc:
        message=str(exc);known=case.get('template_id')=='D03T09' and isinstance(exc,c.pymysql.OperationalError) and exc.args[0]==20102 and KNOWN in message
        result={'id':case['id'],'status':'known_failure' if known else 'error','error':c.safe_error(exc)}
        try:
            with cx.cursor() as q:q.execute('SELECT 1');result['same_connection_healthy']=q.fetchone()==(1,)
        except Exception:result['same_connection_healthy']=False
        if not result['same_connection_healthy']:result['status']='error'
        if known:result['issue']='https://github.com/matrixorigin/matrixone/issues/28298'
    result['elapsed_seconds']=round(time.monotonic()-started,6)
    return result

def execute(cases,state,mode,out,workers=8):
    results=[]
    try:
        with (out/'cases.jsonl').open('w') as log,concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for i,result in enumerate(pool.map(lambda r:run_one(r,state,mode),cases),1):
                log.write(json.dumps(result,ensure_ascii=False)+'\n');results.append(result)
                if i%1000==0:log.flush();print(json.dumps({'completed':i,'statuses':dict(Counter(r['status'] for r in results))}),flush=True)
    finally:
        for cx in CONNECTIONS:
            try:cx.close()
            except Exception:pass
        CONNECTIONS.clear()
    return results
