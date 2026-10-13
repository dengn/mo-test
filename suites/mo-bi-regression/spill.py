"""Million-row spill gates: exact full-output digest, real disk evidence and cleanup."""
import hashlib,json,os,re,threading,time,uuid
from pathlib import Path
import requests
import common as c
import stress

def stream_digest(rows):
    h=hashlib.sha256();count=0
    for row in rows:
        # Preserve the original independent stream hash: dates do not occur in
        # these queries, so scalar transport is identical to the frozen oracle.
        values=[c.scalar(v) for v in row]
        h.update(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
    return {'rows':count,'sha256':h.hexdigest()}

def snapshot(root,pid):
    files={}
    for p in root.rglob('*'):
        try:
            if p.is_file():files[str(p.relative_to(root))]=p.stat().st_size
        except OSError:pass
    # Merge-order files are often unlinked while still open. Directory listings
    # alone would falsely report no spill and miss cleanup obligations.
    for fd in (Path('/proc')/str(pid)/'fd').iterdir():
        try:
            target=os.readlink(fd)
            if str(root) in target and target.endswith(' (deleted)'):
                st=fd.stat();files['@unlinked/'+str(st.st_ino)]=st.st_size
        except OSError:pass
    return files

class Monitor:
    def __init__(self,root,pid):self.root=root;self.pid=pid;self.stop=threading.Event();self.seen={};self.peak=0;self.failure=None
    def loop(self):
        try:
            while not self.stop.is_set():
                files=snapshot(self.root,self.pid);self.peak=max(self.peak,sum(files.values()))
                for path,size in files.items():self.seen[path]=max(size,self.seen.get(path,0))
                self.stop.wait(.005)
        except Exception as exc:self.failure=type(exc).__name__
    def start(self):self.before=snapshot(self.root,self.pid);self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self
    def finish(self):
        self.stop.set();self.thread.join();after=snapshot(self.root,self.pid)
        return {'peak_bytes':self.peak,'seen_files':self.seen,'new_files_remaining':{k:v for k,v in after.items() if k not in self.before},'monitor_error':self.failure}

def metrics(url):
    session=requests.Session()
    from urllib.parse import urlsplit
    if urlsplit(url).hostname in ('localhost','127.0.0.1','::1'):session.trust_env=False
    r=session.get(url,timeout=10);r.raise_for_status()
    return {line.rsplit(' ',1)[0]:float(line.rsplit(' ',1)[1]) for line in r.text.splitlines()
            if line.startswith(('mo_execution_resource_budget_','mo_hash_build_spill')) and not line.startswith('#')}

def run(state,args):
    token=stress.identity(args.mo_pid);root=args.spill_root.resolve()
    if not root.is_dir():raise RuntimeError('Spill directory must be provisioned on the dedicated instance')
    spec=json.loads((c.ROOT/'corpus/spill.json').read_text());db='mo_bi_'+state['run_id']+'_spill_'+uuid.uuid4().hex[:8]
    with c.connection(timeout=180) as cx,cx.cursor() as q:
        q.execute('CREATE DATABASE '+c.identifier(db));state['owned_schemas'].append(db);c.write_json(args.out/'fixture-state.json',state)
        q.execute('USE '+c.identifier(db))
        q.execute('CREATE TABLE fact (id BIGINT,grp INT,k BIGINT,amount DECIMAL(24,6),payload VARCHAR(256))')
        for table in ['build_keys','probe_keys']:q.execute('CREATE TABLE '+table+' (k BIGINT,payload BIGINT) CLUSTER BY k')
        q.execute("INSERT INTO fact SELECT result,MOD(result,131071),MOD(result*7,65521),CAST(MOD(result*37,1000000) AS DECIMAL(24,6))/1000,RPAD(CONCAT('行',CAST(result AS CHAR)),128,'x') FROM generate_series(1,1048576) g")
        q.execute('INSERT INTO build_keys SELECT result,result FROM generate_series(1,65536) g')
        q.execute('INSERT INTO probe_keys SELECT 7,result FROM generate_series(1,65536) g')
        q.execute('INSERT INTO build_keys VALUES (NULL,-3)');q.execute('INSERT INTO probe_keys VALUES (NULL,-1),(65537,-2)')
    results=[]
    queries=list(spec['queries'].items());queries=queries[:args.limit] if args.limit else queries
    for name,sql in queries:
        if stress.identity(args.mo_pid)!=token:raise RuntimeError('Dedicated service identity changed')
        with c.connection(db,timeout=180) as cx:
            with cx.cursor() as q:
                for key,value in [('agg_spill_mem',1048576),('sort_spill_mem',262144),('join_spill_mem',512),('max_dop',2)]:q.execute('SET SESSION '+key+'='+str(value))
                q.execute("SET SESSION optimizer_hints='forceOneCN=1'")
                # Explicit optimizer-fixture estimates force the eligible join
                # path; this changes no input row or reference result.
                for table,n in [('probe_keys',20000000),('build_keys',10000000)]:
                    stats={'table_cnt':n,'block_number':2048,'accurate_object_number':128,'approx_object_number':128,'ndv_map':{'k':n},'min_val_map':{'k':1},'max_val_map':{'k':20000000},
                      'shuffle_range_map':{'k':{'overlap':.1,'uniform':1,'result':[1,5000000,10000000,15000000,20000000]}}}
                    q.execute("SELECT table_cnt FROM table_stats(%s,'patch',%s) g",(db+'.'+table,json.dumps(stats)));q.fetchall()
            before=metrics(args.metrics_url);mon=Monitor(root,args.mo_pid).start();start=time.monotonic();result={'id':'SPILL-'+name,'status':'error'}
            try:
                with cx.cursor(c.pymysql.cursors.SSCursor) as q:
                    q.execute(sql);actual=stream_digest(iter(q.fetchone,None))
                expected=spec['expected'][name];result.update(status='passed' if actual['rows']==expected['rows'] and actual['sha256']==expected['sha256'] else 'mismatch',actual=actual,expected={'rows':expected['rows'],'sha256':expected['sha256']})
            except Exception as exc:result['error']=c.safe_error(exc)
            result['files']=mon.finish();after=metrics(args.metrics_url)
            result['spill_counter_delta']={k:v-before.get(k,0) for k,v in after.items() if v>before.get(k,0) and 'spill' in k.lower()}
            try:
                with cx.cursor() as q:q.execute('EXPLAIN (ANALYZE TRUE) '+sql);plan='\n'.join(str(v) for row in q.fetchall() for v in row)
                result['positive_plan_spill']=bool(re.search(r'Spill(?:Size|Rows)[:=]\s*[1-9][0-9]*(?:\.[0-9]+)?',plan))
                (args.out/(name+'.plan.txt')).write_text(plan)
            except Exception as exc:result['explain_error']=c.safe_error(exc)
            result['spill_observed']=bool(result['files']['peak_bytes'] or result['spill_counter_delta'] or result.get('positive_plan_spill'))
            result['expected_spill']=name!='join_not_in_null'
            # NOT IN with NULL in its right input is a deliberate empty-result
            # control. Its null-aware plan short-circuits without spill; forcing
            # disk activity here would reward unnecessary work.
            evidence_ok=result['spill_observed'] if result['expected_spill'] else not result['spill_observed']
            # A completed SQL query cannot satisfy a spill gate without actual
            # spill evidence and a clean process-local file boundary.
            if result['status']=='passed' and (not evidence_ok or result['files']['new_files_remaining'] or result['files']['monitor_error']):result['status']='spill_evidence_missing_or_dirty'
            with cx.cursor() as q:q.execute('SELECT 1');result['same_connection_healthy']=q.fetchone()==(1,)
            if not result['same_connection_healthy']:result['status']='error'
            result['elapsed_seconds']=round(time.monotonic()-start,6);results.append(result)
    return results
