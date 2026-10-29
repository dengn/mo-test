import json,os,subprocess,time
from pathlib import Path
base=Path.cwd(); env=os.environ.copy();env.update(LD_LIBRARY_PATH=str(base/'odbc-sdk/usr/lib/x86_64-linux-gnu'),ODBCSYSINI=str(base/'odbc-conf'),ODBCINSTINI='odbcinst.ini')
common='SERVER=127.0.0.1;UID=root;PWD=111;SSLMODE=DISABLED'
cases=[('smoke-unicode','mo_odbc_smoke','DRIVER={MatrixOne ODBC 9.7 Unicode Driver};DATABASE=mo_odbc_smoke;'+common,{}),('auth-sqlstate','mo_odbc_smoke','DRIVER={MatrixOne ODBC 9.7 Unicode Driver};DATABASE=mo_odbc_smoke;'+common.replace('PWD=111','PWD=wrong'),{'MO_ODBC_EXPECT_SQLSTATE':'28000'}),('deep-unicode','mo_odbc_deep','DRIVER={MatrixOne ODBC 9.7 Unicode Driver};'+common,{}),('deep-ansi','mo_odbc_deep','DRIVER={MatrixOne ODBC 9.7 ANSI Driver};'+common,{})]
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','odbc_sha':'6168fe4a7fb428fb993a4817dc4457f2825ba069','mysql_client':'8.0.46','unixodbc':'2.3.12','cases':[]}
for name,exe,conn,extra in cases:
 e=env.copy();e['MO_ODBC_CONNECTION_STRING']=conn;e.update(extra);start=time.monotonic()
 with open('odbc-'+name+'.log','w') as f:
  try:r=subprocess.run([str(base/'odbc-build/test'/exe)],env=e,stdout=f,stderr=subprocess.STDOUT,timeout=120);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 result={'name':name,'exit_code':code,'status':'passed' if code==0 else 'failed','duration_seconds':round(time.monotonic()-start,3)}
 text=Path('odbc-'+name+'.log').read_text();result['tap']=[s for s in text.splitlines() if s.startswith(('ok ','not ok ','# summary','Bail out!'))]
 out['cases'].append(result);print(name,code,flush=True)
 Path('odbc-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
out['status']='passed' if all(c['status']=='passed' for c in out['cases']) else 'failed'
Path('odbc-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
