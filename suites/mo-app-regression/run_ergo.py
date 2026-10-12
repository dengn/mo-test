"""Native IRC account/channel workflow and MatrixOne-backed persistent chat history.

The upstream BuntDB account/channel store remains native; only the documented
MySQL history backend is pointed at MatrixOne. No SQL proxy or migration stamps.
"""
import argparse,base64,hashlib,io,json,os,secrets,select,signal,socket,subprocess,tarfile,time,urllib.request,uuid,xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parent
SHA='680545a7902b169386160412469097cc63c362b75e85bee2206898d800886a4e'
ARCHIVE_SHA='c275f2de8e8eb074c38707136392290172400b5b78616cb9f660351527924b47'

class IRC:
    def __init__(self,port,nick,password=None):
        self.sock=socket.create_connection(('127.0.0.1',port),timeout=10)
        self.sock.setblocking(False);self.buf=b'';self.nick=nick
        if password:self.send('PASS '+nick+':'+password)
        self.send('CAP LS 302');self.send('NICK '+nick);self.send('USER '+nick+' 0 * :Native regression')
        self.until(lambda s:' CAP ' in s and ' LS ' in s)
        self.send('CAP REQ :message-tags server-time batch draft/chathistory echo-message')
        self.until(lambda s:' CAP ' in s and (' ACK ' in s or ' NAK ' in s))
        if ' NAK ' in self.lines[-1]:raise AssertionError('required native IRC capabilities')
        self.send('CAP END');self.until(lambda s:' 001 ' in s)
    def send(self,text):
        self.sock.setblocking(True);self.sock.settimeout(10)
        try:self.sock.sendall(text.encode()+b'\r\n')
        finally:self.sock.setblocking(False)
    def until(self,predicate,timeout=20):
        self.lines=[];deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            while b'\n' in self.buf:
                b,self.buf=self.buf.split(b'\n',1);line=b.rstrip(b'\r').decode('utf8');self.lines.append(line)
                if line.startswith('PING '):self.send('PONG '+line[5:])
                if predicate(line):return self.lines
                if line.startswith('ERROR '):raise RuntimeError('Native IRC disconnected')
            ready,_,_=select.select([self.sock],[],[],min(1,max(0,deadline-time.monotonic())))
            if ready:
                b=self.sock.recv(65536)
                if not b:raise RuntimeError('Native IRC connection closed')
                self.buf+=b
        raise TimeoutError('native IRC response deadline')
    def close(self):self.sock.close()

def main():
    import pymysql
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path);p.add_argument('--messages',type=int,default=16);p.add_argument('--writers',type=int,default=2);p.add_argument('--disable-fakelag',action='store_true',help='Separate load profile bypassing only native command-rate delay');p.add_argument('--out',type=Path,default=ROOT/'artifacts'/('ergo-'+uuid.uuid4().hex[:12]));a=p.parse_args()
    if not 1<=a.messages<=4096 or not 1<=a.writers<=64:p.error('Bounds: messages 1..4096, writers 1..64')
    if 'MO_PASSWORD' not in os.environ:p.error('MO_PASSWORD is required')
    a.out.mkdir(parents=True,exist_ok=False);schema='mo_reg_ergo_'+uuid.uuid4().hex[:16];private=ROOT/'runtime'/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'ergochat/ergo','version':'v2.19.1','commit':'63c743a70644f0f19109508ade8580bf37f7d23d','binary_sha256':SHA,'schema':schema,'native_runtime_attempted':False,'source_edits':False,'SQL_scope':'documented persistent history only; native BuntDB account/channel store retained','native_fakelag_retained':not a.disable_fakelag,'checks':[],'attempts':[],'passed':False};proc=None;log=None;clients=[];stage='binary'
    cfg=dict(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.environ['MO_PASSWORD'],charset='utf8mb4',autocommit=True,connect_timeout=10,read_timeout=30)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    owner='mo_owner';password=secrets.token_urlsafe(24);channel='#mo-'+uuid.uuid4().hex[:12];cohort=uuid.uuid4().hex[:12];messages=[f'{cohort}-{i}: 中文 😀𠮷' for i in range(a.messages)]
    def check(name,value,**extra):
        report['checks'].append({'name':name,'passed':bool(value),**extra})
        if not value:raise AssertionError(name)
    def stop():
        nonlocal proc
        for c in clients:c.close()
        clients.clear()
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=12)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        proc=None
    try:
        app=a.binary or ROOT/'runtime/ergo-v2.19.1/ergo'
        if not app.exists():
            with urllib.request.urlopen('https://github.com/ergochat/ergo/releases/download/v2.19.1/ergo-2.19.1-linux-x86_64.tar.gz',timeout=90) as r:data=r.read(16*1024**2)
            assert hashlib.sha256(data).hexdigest()==ARCHIVE_SHA
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as t:
                m=next(m for m in t.getmembers() if m.isfile() and m.name.split('/')[-1]=='ergo');data=t.extractfile(m).read()
            app.parent.mkdir(parents=True,exist_ok=True);app.write_bytes(data);app.chmod(0o700)
        check('pinned_native_binary',hashlib.sha256(app.read_bytes()).hexdigest()==SHA)
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:q.execute('SELECT VERSION()');report['server_version']=q.fetchone()[0];check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'`')
        conf=json.loads((ROOT/'fixtures/ergo-v2.19.1/upstream-defaults.json').read_text())
        conf['server']['listeners']={'127.0.0.1:'+str(port):None};conf['server']['name']='mo-regression.test';conf['network']['name']='MORegression';conf['languages']['enabled']=False;conf['datastore']['path']=str(private/'native-accounts.db');conf['lock-file']=str(private/'native.lock');conf['history']['persistent']['enabled']=True;conf['logging'][0]['level']='warn'
        conf['datastore']['mysql'].update(enabled=True,host=cfg['host'],port=cfg['port'],user=cfg['user'],password=cfg['password'],**{'history-database':schema})
        if a.disable_fakelag:conf['fakelag']['enabled']=False
        confpath=private/'private-config.yaml';confpath.write_text(json.dumps(conf,ensure_ascii=False));confpath.chmod(0o600)
        env={k:v for k,v in os.environ.items() if not k.startswith('ERGO__')};env.update(GOMAXPROCS='2',GOMEMLIMIT='512MiB');log=os.fdopen(os.open(private/'native.log',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb')
        def start():
            nonlocal proc
            proc=subprocess.Popen([str(app),'run','--conf',str(confpath)],cwd=private,env=env,stdout=log,stderr=log,start_new_session=True);report['native_runtime_attempted']=True
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native initialization exited; private log retained')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=1):return
                except OSError:time.sleep(.2)
            raise TimeoutError('native startup')
        stage='native_initialization';start()
        with pymysql.connect(**cfg,database=schema) as conn:
            with conn.cursor() as q:q.execute('SELECT key_name,value FROM metadata ORDER BY key_name');check('native_schema_versions',q.fetchall()==(('db.minorversion','2'),('db.version','2')));q.execute('SHOW TABLES');report['native_tables']=[r[0] for r in q.fetchall()]
        stage='native_registration';alice=IRC(port,owner);clients.append(alice);alice.send('PRIVMSG NickServ :REGISTER '+password);lines=alice.until(lambda s:'NickServ' in s and ('Account created' in s or 'error' in s.lower()));check('native_account_registration',any('Account created' in s for s in lines))
        alice.send('JOIN '+channel);alice.until(lambda s:' 366 ' in s);alice.send('PRIVMSG ChanServ :REGISTER '+channel);lines=alice.until(lambda s:'ChanServ' in s and ('registered' in s.lower() or 'error' in s.lower()));check('native_channel_registration',any('registered' in s.lower() for s in lines))
        alice.send('MODE '+channel+' +s');alice.until(lambda s:' MODE '+channel+' ' in s)
        stage='native_access_denial';outsider=IRC(port,'mo_outsider');clients.append(outsider);outsider.send('CHATHISTORY LATEST '+channel+' * 10');lines=outsider.until(lambda s:' FAIL CHATHISTORY ' in s or ' BATCH -' in s);check('nonmember_history_denied',any(' FAIL CHATHISTORY INVALID_TARGET ' in s for s in lines))
        stage='native_messages';writers=[]
        for _ in range(a.writers):
            c=IRC(port,owner,password);clients.append(c);writers.append(c)
        def write_group(w):
            c=writers[w]
            for i in range(w,a.messages,a.writers):
                item={'index':i,'message':messages[i],'acknowledged':False};report['attempts'].append(item)
                try:
                    c.send('PRIVMSG '+channel+' :'+messages[i]);c.until(lambda s:(' PRIVMSG '+channel+' :'+messages[i]) in s);item['acknowledged']=True
                except Exception as e:item['error_type']=type(e).__name__
        t=time.monotonic()
        with ThreadPoolExecutor(max_workers=a.writers) as pool:list(pool.map(write_group,range(a.writers)))
        check('native_echo_acknowledgments',len(report['attempts'])==a.messages and all(x['acknowledged'] for x in report['attempts']),messages=a.messages,writers=a.writers,seconds=round(time.monotonic()-t,4))
        def rows():
            with pymysql.connect(**cfg,database=schema) as conn:
                with conn.cursor() as q:q.execute('SELECT h.id,h.data,h.msgid,s.target,s.nanotime FROM history h JOIN sequence s ON s.history_id=h.id WHERE s.target=%s ORDER BY h.id',(channel.encode(),));return q.fetchall()
        def audit(label):
            deadline=time.monotonic()+30
            while True:
                data=rows();owned=[(r,json.loads(r[1])) for r in data if json.loads(r[1]).get('Message',{}).get('Message','').startswith(cohort+'-')]
                if len(owned)>=a.messages or time.monotonic()>deadline:break
                time.sleep(.2)
            actual={j['Message']['Message'] for r,j in owned};check(label,len(owned)==len(actual)==a.messages and actual==set(messages) and all(j['AccountName']==owner and j['Type']==1 and r[3]==channel.encode() and len(r[2])==16 and base64.b32encode(r[2]).decode().rstrip('=').translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567','abcdefghijkmnpqrstuvwxyz23456789'))==j['Message']['Msgid'] for r,j in owned));return [(r[0],hashlib.sha256(r[1]).hexdigest(),r[2].hex(),r[3].hex(),r[4]) for r,j in owned]
        stage='native_SQL_audit';before=audit('SQL_exact_Unicode_binary_msgid_and_channel_links')
        def replay(c,label):
            result=[];param='LATEST '+channel+' * 1000'
            for _ in range((a.messages+999)//1000+2):
                c.send('CHATHISTORY '+param);lines=c.until(lambda s:' BATCH -' in s or ' FAIL CHATHISTORY ' in s,timeout=30)
                if any(' FAIL CHATHISTORY ' in s for s in lines):raise AssertionError('native history retrieval')
                # Pending live echo messages may precede the response. Count only
                # messages tagged with the batch opened by this history query.
                batch_ids={s.split(' BATCH +',1)[1].split(' ',1)[0] for s in lines if ' BATCH +' in s}
                relevant=[s for s in lines if ' PRIVMSG '+channel+' :' in s and s.startswith('@') and any(v=='batch='+bid for v in s.split(' ',1)[0][1:].split(';') for bid in batch_ids)];result.extend(s.split(' PRIVMSG '+channel+' :',1)[1] for s in relevant)
                if len(relevant)<1000:break
                tags=dict(v.split('=',1) for v in relevant[0].split(' ',1)[0].lstrip('@').split(';') if '=' in v);param='BEFORE '+channel+' msgid='+tags['msgid']+' 1000'
            found=[v for v in result if v.startswith(cohort+'-')];check(label,len(found)==a.messages and len(set(found))==a.messages and set(found)==set(messages))
        stage='native_history';replay(alice,'native_CHATHISTORY_exact_messages')
        stage='native_restart';old=proc.pid;stop();start();check('real_process_restart',proc.pid!=old);alice=IRC(port,owner,password);clients.append(alice);alice.send('JOIN '+channel);alice.until(lambda s:' 366 ' in s);after=audit('restart_SQL_exact_messages');check('restart_original_row_bytes_and_identifiers',before==after);replay(alice,'restart_native_authenticated_history');report['passed']=True
    except Exception as e:
        report.update(error_type=type(e).__name__,failed_stage=stage)
        if isinstance(e,AssertionError):report['failed_check']=str(e)
        report['last_protocol_responses']=[line.replace(password,'<redacted>').replace(cfg['password'],'<redacted>') for c in clients for line in getattr(c,'lines',[])][-12:]
    finally:
        stop()
        if log:log.close()
    report['time_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());report['attempts'].sort(key=lambda x:x['index']);(a.out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));checks=report['checks'][:]
    if not report['passed'] and all(x['passed'] for x in checks):checks.append({'name':'native_execution','passed':False})
    suite=ET.Element('testsuite',name='ergo-native',tests=str(len(checks)),failures=str(sum(not x['passed'] for x in checks)))
    for c in checks:
        tc=ET.SubElement(suite,'testcase',name=c['name'],classname='ergo.native')
        if not c['passed']:ET.SubElement(tc,'failure',message=c['name'])
    ET.ElementTree(suite).write(a.out/'junit.xml',encoding='utf-8',xml_declaration=True);print(json.dumps({'passed':report['passed'],'native_runtime_attempted':report['native_runtime_attempted'],'schema':schema,'failed_stage':report.get('failed_stage'),'error_type':report.get('error_type'),'failed_check':report.get('failed_check')}));return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
