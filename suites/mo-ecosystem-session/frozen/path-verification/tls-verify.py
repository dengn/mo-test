import pymysql,ssl,json,os,subprocess,time,traceback
from pathlib import Path
root=Path.cwd();ca=str(root/'tls/ca.crt');badca=str(root/'tls/untrusted.crt')
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','cases':[]}
def connect(host='localhost',cafile=ca):return pymysql.connect(host=host,port=6001,user='root',password='111',database='mo_odbc_smoke',autocommit=True,ssl_ca=cafile,ssl_verify_cert=True,ssl_verify_identity=True,connect_timeout=5)
try:
 with connect() as d:
  assert isinstance(d._sock,ssl.SSLSocket)
  out['cases'].append({'name':'native-tls-verified-connection','status':'passed','tls_version':d._sock.version(),'cipher':d._sock.cipher()[0]})
  actual={}
  with d.cursor() as c:
   for table in json.loads(Path('restart-before.json').read_text()):
    c.execute('SELECT COUNT(*) FROM '+table);actual[table]=c.fetchone()[0]
  expected=json.loads(Path('restart-before.json').read_text())
  out['cases'].append({'name':'matrixone-restart-row-count-recovery','expected':expected,'actual':actual,'status':'passed' if expected==actual else 'failed'})
  with d.cursor() as c:
   try:c.execute('DROP DATABASE raw_name_probe');out['raw_name_drop_after_restart']={'status':'passed'}
   except Exception as e:out['raw_name_drop_after_restart']={'status':'failed','error':str(e)[:1400]}
 for name,h,cafile in [('native-untrusted-ca-rejected','localhost',badca),('native-hostname-mismatch-rejected','127.0.0.1',ca)]:
  try:
   with connect(h,cafile):pass
   out['cases'].append({'name':name,'status':'failed','error':'Untrusted or mismatching certificate accepted'})
  except Exception as e:
   text=str(e);out['cases'].append({'name':name,'status':'passed' if 'CERTIFICATE_VERIFY_FAILED' in text else 'failed','error':text})
 env=os.environ.copy();env.update(ODBCSYSINI=str(root/'odbc-conf'),ODBCINSTINI='odbcinst.ini',LD_LIBRARY_PATH=str(root/'odbc-sdk/usr/lib/x86_64-linux-gnu'))
 for name,h,cafile,positive in [('odbc-tls-verify-identity','localhost',ca,True),('odbc-untrusted-ca-rejected','localhost',badca,False),('odbc-hostname-mismatch-rejected','127.0.0.1',ca,False)]:
  e=env.copy();e['MO_ODBC_CONNECTION_STRING']=f'DRIVER={{MatrixOne ODBC 9.7 Unicode Driver}};SERVER={h};DATABASE=mo_odbc_smoke;UID=root;PWD=111;SSLMODE=VERIFY_IDENTITY;SSLCA={cafile}'
  with open(name+'.log','w') as f:r=subprocess.run([str(root/'odbc-build/test/mo_odbc_smoke')],env=e,stdout=f,stderr=subprocess.STDOUT,timeout=30)
  text=Path(name+'.log').read_text();good=(r.returncode==0) if positive else (r.returncode!=0 and any(s in text.lower() for s in ['certificate verify failed','certificate validation failure','identity','does not match','ssl connection error']))
  out['cases'].append({'name':name,'status':'passed' if good else 'failed','exit_code':r.returncode,'result_lines':[s for s in text.splitlines() if s.startswith(('RESULT','FAIL','PASS SQLDriverConnect'))]})
 out['status']='passed' if all(c['status']=='passed' for c in out['cases']) else 'failed'
except Exception as e:out.update(status='failed',error=str(e));traceback.print_exc()
Path('tls-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if out['status']!='passed':raise SystemExit(1)
