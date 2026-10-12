import os,subprocess,json,time
from pathlib import Path
root=Path.cwd();env=os.environ.copy();env.update(ODBCSYSINI=str(root/'odbc-conf'),ODBCINSTINI='odbcinst.ini',LD_LIBRARY_PATH=str(root/'odbc-sdk/usr/lib/x86_64-linux-gnu'))
out={'fixture_override':'1 MiB streaming payload column TEXT -> LONGTEXT; original pinned test failures retained','ansi_override':'CHARSET=utf8mb4','cases':[]}
for name,driver,suffix in [('unicode','Unicode',''),('ansi','ANSI',';CHARSET=utf8mb4')]:
 e=env.copy();e['MO_ODBC_CONNECTION_STRING']=f'DRIVER={{MatrixOne ODBC 9.7 {driver} Driver}};SERVER=127.0.0.1;UID=root;PWD=111;SSLMODE=DISABLED'+suffix
 with open('odbc-'+name+'-adapted.log','w') as f:r=subprocess.run([str(root/'mo_odbc_deep_longtext')],env=e,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 text=Path('odbc-'+name+'-adapted.log').read_text();out['cases'].append({'name':name,'exit_code':r.returncode,'status':'passed' if r.returncode==0 else 'failed','tap':[s for s in text.splitlines() if s.startswith(('ok ','not ok ','# summary','Bail out!'))]})
 print(name,r.returncode,flush=True);Path('odbc-adapted-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
out['status']='passed' if all(c['status']=='passed' for c in out['cases']) else 'failed';Path('odbc-adapted-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
