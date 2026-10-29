from runtime import *
import concurrent.futures
exe=str(B/'redpanda-connect/redpanda-connect')
schema='(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(80),name VARCHAR(300),ts DATETIME(6),doc JSON)'
rows=[(1,9007199254740993,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','RPC中文😀','2026-10-11 12:00:00.123456','{"big":9007199254740993}'),(2,-2**63,0,'-0.000000000000000001',b'','','2026-10-11 00:00:00','[]'),(3,None,None,None,None,None,None,None)]
for p in [6001,13306]:
 sql(p,'eco4','CREATE TABLE rpc_source'+schema)
 with db(p) as d,d.cursor() as c:c.executemany('INSERT INTO rpc_source VALUES('+','.join(['%s']*8)+')',rows)
out={'runtime_ref':REF,'tool':'Redpanda Connect 4.113.0','scope':'native Go SQL select/insert, actual process full run; four cross-engine pairs; prepared parameters','cases':[]}
def norm(rr):
 n=[]
 for row in rr:
  r=list(row);r[-1]=json.loads(r[-1]) if isinstance(r[-1],str) else r[-1]
  if r[-2] and r[-2].endswith('.000000'):r[-2]=r[-2][:-7]
  n.append(r)
 return n
cols='id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc'
for src,dst in [(13306,13306),(13306,6001),(6001,6001),(6001,13306)]:
 target=f'rpc_sink_{src}_{dst}';sql(dst,'eco4','CREATE TABLE '+target+schema)
 def dsn(p):return f"root:{'111' if p==6001 else 'types-local'}@tcp(127.0.0.1:{p})/eco4?parseTime=true&loc=UTC&timeout=5s&readTimeout=15s&writeTimeout=15s"
 cfg={'http':{'enabled':False},'input':{'sql_select':{'driver':'mysql','dsn':dsn(src),'table':'rpc_source','columns':['id','s','u','d','payload','name','ts','doc']}},'pipeline':{'threads':1},'output':{'sql_insert':{'driver':'mysql','dsn':dsn(dst),'table':target,'columns':['id','s','u','d','payload','name','ts','doc'],'args_mapping':'root = [this.id,this.s,this.u,this.d,this.payload,this.name,this.ts,this.doc]','suffix':'ON DUPLICATE KEY UPDATE s=VALUES(s),u=VALUES(u),d=VALUES(d),payload=VALUES(payload),name=VALUES(name),ts=VALUES(ts),doc=VALUES(doc)'}},'logger':{'level':'INFO'},'shutdown_timeout':'5s'}
 config=B/(target+'.json');dump(config,cfg);r={'source_port':src,'target_port':dst,'config':config.name}
 try:
  with (B/(target+'.log')).open('wb') as f:
   proc=subprocess.run([exe,'run',str(config)],stdout=f,stderr=subprocess.STDOUT,timeout=35)
  r['exit_code']=proc.returncode
 except subprocess.TimeoutExpired:r['timed_out']=True
 source=norm(sql(src,'eco4','SELECT '+cols+' FROM rpc_source ORDER BY id'));actual=norm(sql(dst,'eco4','SELECT '+cols+' FROM '+target+' ORDER BY id'));r.update({'source_rows':source,'target_rows':actual,'all_fields_equal':source==actual,'log_tail':(B/(target+'.log')).read_text()[-3000:],'status':'passed' if source==actual and r.get('exit_code')==0 else 'failed'})
 out['cases'].append(r);dump(B/'redpanda-sql-result.json',out);print('RPC SQL',src,dst,r['status'],r.get('exit_code'),flush=True)
