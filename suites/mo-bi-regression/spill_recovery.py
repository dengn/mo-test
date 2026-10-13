"""Managed spill fault tests; start/stop only children created by this runner."""
import argparse,concurrent.futures,hashlib,json,os,re,shutil,socket,subprocess,sys,time,tomllib,uuid
from pathlib import Path
import common as c
import run as reporting
import spill

def local_configs(source,dest):
    source=source.resolve()
    if not (source/'launch.toml').is_file() or not (source/'cn.toml').is_file():raise RuntimeError('Local launch.toml and cn.toml are required')
    launch=tomllib.loads((source/'launch.toml').read_text())
    if launch.get('cnservices')!=['./config/cn.toml']:raise RuntimeError('Managed profile requires one local CN config')
    for role in ['logservices','tnservices','cnservices']:
        for name in launch.get(role,[]):
            if not name.startswith('./config/') or '/' in name.removeprefix('./config/'):raise RuntimeError('Only copied local role configurations are allowed')
    def validate(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key=='data-dir' and (Path(value).is_absolute() or '..' in Path(value).parts):raise RuntimeError('Data directories must stay inside the new owned runtime')
                if key=='fileservice':
                    for service in value:
                        if str(service.get('backend','')).upper() not in ('DISK','DISK-V2'):raise RuntimeError('Managed regression only permits local DISK file services')
                validate(value)
        elif isinstance(node,list):
            for child in node:validate(child)
    dest.mkdir(mode=0o700)
    for path in source.glob('*.toml'):
        parsed=tomllib.loads(path.read_text());validate(parsed)
        for address in parsed.get('hakeeper-client',{}).get('service-addresses',[]):
            if address.rsplit(':',1)[0].strip('[]') not in ('127.0.0.1','localhost','::1'):raise RuntimeError('Managed profile must not join a remote cluster')
        target=dest/path.name;target.write_bytes(path.read_bytes());target.chmod(0o600)

def make_phase(base,memory,capacity):
    text=base
    if '[cn.frontend]' not in text:raise RuntimeError('cn.frontend section required')
    block=text.split('[cn.frontend]',1)[1].split('\n[',1)[0]
    for name,value in [('processLimitationSize',memory),('processLimitationSpillSize',capacity)]:
        pattern=r'(?m)^'+name+r'\s*=.*$'
        if re.search(pattern,block):block=re.sub(pattern,name+' = '+str(value),block)
        else:block+='\n'+name+' = '+str(value)+'\n'
    tail=text.split('[cn.frontend]',1)[1]
    after='\n['+tail.split('\n[',1)[1] if '\n[' in tail else ''
    return text.split('[cn.frontend]',1)[0]+'[cn.frontend]'+block+after

class Instance:
    def __init__(self,binary,root,base,port,metrics_port):self.binary=binary;self.root=root;self.base=base;self.port=port;self.metrics_port=metrics_port;self.proc=None
    def start(self,phase,memory,capacity):
        ports={self.port,self.metrics_port}
        for path in (self.root/'config').glob('*.toml'):
            parsed=tomllib.loads(path.read_text())
            for key in ('cn','tn','logservice'):
                base=parsed.get(key,{}).get('port-base')
                if base:ports.update(range(base,base+10))
        for port in sorted(ports):
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                try:s.bind(('127.0.0.1',port))
                except OSError:raise RuntimeError('Managed instance port already in use; refusing to affect an existing service')
        (self.root/'config/cn.toml').write_text(make_phase(self.base,memory,capacity))
        log=(self.root/(phase+'.log')).open('w')
        self.proc=subprocess.Popen([str(self.binary),'-launch','./config/launch.toml'],cwd=self.root,stdout=log,stderr=subprocess.STDOUT);log.close()
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if self.proc.poll() is not None:raise RuntimeError('Owned MatrixOne exited during startup')
            try:
                with c.connection(timeout=3) as cx,cx.cursor() as q:q.execute('SELECT 1')
                return self.proc.pid
            except Exception:time.sleep(.2)
        raise RuntimeError('Owned MatrixOne startup timeout')
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=10)
        self.proc=None

def settings(cx,db,forced):
    with cx.cursor() as q:
        for name,value in [('agg_spill_mem',1048576 if forced else 1073741824),('sort_spill_mem',262144 if forced else 1073741824),('join_spill_mem',512 if forced else 1073741824),('max_dop',2)]:q.execute('SET SESSION '+name+'='+str(value))
        q.execute("SET SESSION optimizer_hints='forceOneCN=1'")

def fixture(db):
    with c.connection(timeout=180) as cx,cx.cursor() as q:
        q.execute('CREATE DATABASE '+c.identifier(db));q.execute('USE '+c.identifier(db))
        q.execute('CREATE TABLE fact (id BIGINT,grp INT,k BIGINT,amount DECIMAL(24,6),payload VARCHAR(256))')
        q.execute("INSERT INTO fact SELECT result,MOD(result,131071),MOD(result*7,65521),CAST(MOD(result*37,1000000) AS DECIMAL(24,6))/1000,RPAD(CONCAT('行',CAST(result AS CHAR)),128,'x') FROM generate_series(1,1048576) g")
    with c.connection(db,timeout=180) as cx,cx.cursor(c.pymysql.cursors.SSCursor) as q:
        q.execute('SELECT id,k,amount FROM fact ORDER BY k DESC,id');actual=spill.stream_digest(iter(q.fetchone,None))
    expected=json.loads((c.ROOT/'corpus/spill.json').read_text())['expected']['sort_narrow']
    if actual['sha256']!=expected['sha256'] or actual['rows']!=expected['rows']:raise RuntimeError('Managed million-row fixture differs from independent reference')

def resource_rejection(exc,kind,limit):
    if not isinstance(exc,c.pymysql.OperationalError):return False
    message=str(exc)
    signature='allocation account capacity exceeded' if kind=='memory' else 'spill disk budget exceeded'
    if signature not in message:return False
    numbers={k:int(v) for k,v in re.findall(r'(used|requested|limit)=(\d+)',message)}
    return numbers.get('limit')==limit and numbers.get('used',0)+numbers.get('requested',0)>limit

def query(db,pid,root,name,sql,expected=None,reject=None):
    with c.connection(db,timeout=180) as cx:
        settings(cx,db,True);mon=spill.Monitor(root,pid).start();start=time.monotonic();r={'id':name,'status':'error'}
        try:
            with cx.cursor(c.pymysql.cursors.SSCursor) as q:q.execute(sql);actual=spill.stream_digest(iter(q.fetchone,None))
            r['actual']=actual
            if expected and actual['sha256']==expected['sha256'] and actual['rows']==expected['rows']:
                r['status']='passed'
                if reject:r['resource_boundary_acceptance']=True
            else:r['status']='mismatch'
        except Exception as exc:
            r['error']=c.safe_error(exc)
            if reject and resource_rejection(exc,*reject):r.update(status='passed',expected_rejection=True)
        r['files']=mon.finish()
        with cx.cursor() as q:q.execute('SELECT 1');r['same_connection_healthy']=q.fetchone()==(1,)
        if not r['same_connection_healthy'] or r['files']['new_files_remaining'] or r['files']['monitor_error']:r['status']='error'
        if not reject and not r['files']['peak_bytes']:r['status']='spill_evidence_missing_or_dirty'
        r['elapsed_seconds']=round(time.monotonic()-start,6);return r

def cancellation(db,pid,root):
    cx=c.connection(db,timeout=180);settings(cx,db,True);cid=cx.thread_id();mon=spill.Monitor(root,pid).start();start=time.monotonic();r={'id':'RECOVERY-CANCEL-OBSERVED-SPILL','status':'error'}
    def worker():
        try:
            with cx.cursor(c.pymysql.cursors.SSCursor) as q:
                q.execute('SELECT id,k,amount,payload FROM fact ORDER BY payload DESC,id')
                for _ in iter(q.fetchone,None):pass
            return None
        except Exception as e:return e
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        job=pool.submit(worker);deadline=time.monotonic()+20
        while time.monotonic()<deadline and not job.done() and not mon.seen:time.sleep(.005)
        r['spill_before_cancel']=bool(mon.seen)
        if r['spill_before_cancel'] and not job.done():
            with c.connection(timeout=10) as ctrl,ctrl.cursor() as q:q.execute('KILL QUERY '+str(cid));r['cancel_sent']=True
        error=job.result(timeout=30)
        r['cancellation_error']=c.safe_error(error) if error else None
    r['files']=mon.finish()
    try:
        with cx.cursor() as q:q.execute('SELECT 1');r['same_connection_healthy']=q.fetchone()==(1,)
        if r.get('cancel_sent') and error and 'cancel' in str(error).lower() and r['same_connection_healthy'] and not r['files']['new_files_remaining'] and not r['files']['monitor_error']:r['status']='passed'
    finally:cx.close()
    r['elapsed_seconds']=round(time.monotonic()-start,6);return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--binary-sha256',required=True);p.add_argument('--config-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--dedicated-instance',action='store_true',required=True);p.add_argument('--expected-commit');a=p.parse_args()
    if os.getenv('MO_HOST','127.0.0.1') not in ('127.0.0.1','localhost'):p.error('Managed recovery requires a local owned instance')
    if a.out.exists():p.error('Output exists; choose a new directory')
    if hashlib.sha256(a.binary.read_bytes()).hexdigest()!=a.binary_sha256:p.error('MatrixOne binary identity mismatch')
    if shutil.disk_usage(a.out.parent if a.out.parent.exists() else c.ROOT).free<2048*1024**2:p.error('Managed recovery requires at least 2 GiB free disk space')
    a.out.mkdir(parents=True,mode=0o700);root=c.ROOT/'runtime'/('spill-recovery-'+uuid.uuid4().hex[:16]);root.mkdir(parents=True,mode=0o700)
    local_configs(a.config_dir,root/'config');base=(root/'config/cn.toml').read_text();parsed=tomllib.loads(base)
    port=parsed.get('cn',{}).get('frontend',{}).get('port',6001);metrics_port=parsed.get('observability',{}).get('status-port',7001)
    if port!=int(os.getenv('MO_PORT','6001')):p.error('Frontend config port differs from MO_PORT')
    instance=Instance(a.binary.resolve(),root,base,port,metrics_port);db='mo_bi_recovery_'+uuid.uuid4().hex[:16];records=[];meta={'profile':'spill-recovery','binary_sha256':a.binary_sha256,'target':None,'phases':[],'owned_processes_only':True}
    spec=json.loads((c.ROOT/'corpus/spill.json').read_text())
    local_service=next((s for s in parsed.get('fileservice',[]) if s.get('name')=='LOCAL'),None)
    if not local_service or not local_service.get('data-dir'):p.error('Managed recovery requires a local LOCAL file-service data-dir')
    spill_root=root/local_service['data-dir']/'__spill'
    try:
        from verify import verify
        meta['corpus_integrity']=verify()
        pid=instance.start('forced-128m',134217728,1073741824);meta['target']=c.preflight(a.expected_commit);fixture(db)
        meta['phases'].append({'name':'forced','memory_cap_bytes':134217728,'spill_cap_bytes':1073741824})
        records.append(query(db,pid,spill_root,'RECOVERY-FORCED-SORT',spec['queries']['sort_wide'],spec['expected']['sort_wide']))
        records.append(cancellation(db,pid,spill_root))
        records.append(query(db,pid,spill_root,'RECOVERY-WIDE-128M','SELECT id,k,amount,payload FROM fact ORDER BY payload DESC,id',expected=spec['million_wide_expected'],reject=('memory',134217728)))
        instance.stop()
        pid=instance.start('lowdisk',134217728,1048576);meta['phases'].append({'name':'lowdisk','memory_cap_bytes':134217728,'spill_cap_bytes':1048576})
        for name in ['sort_wide','aggregate_high_cardinality']:
            records.append(query(db,pid,spill_root,'RECOVERY-LOWDISK-'+name,spec['queries'][name],expected=spec['expected'][name],reject=('disk',1048576)))
        instance.stop()
        pid=instance.start('wide-512m',536870912,1073741824);meta['phases'].append({'name':'wide-512m','memory_cap_bytes':536870912,'spill_cap_bytes':1073741824})
        records.append(query(db,pid,spill_root,'RECOVERY-WIDE-512M','SELECT id,k,amount,payload FROM fact ORDER BY payload DESC,id',spec['million_wide_expected']))
    except Exception as exc:records.append({'id':'RECOVERY-HARNESS','status':'error','error':c.safe_error(exc)})
    finally:instance.stop()
    return reporting.report(a.out,records,meta,'strict')

if __name__=='__main__':sys.exit(main())
