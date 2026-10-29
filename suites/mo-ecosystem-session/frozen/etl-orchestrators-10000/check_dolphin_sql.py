import pathlib,json,requests,pymysql
B=pathlib.Path(__file__).resolve().parent;ids=json.loads((B/'dolphin-sql-runtime-ids.json').read_text());s=requests.Session();s.headers['sessionId']=ids['session_id'];base='http://127.0.0.1:12345/dolphinscheduler/projects/'+str(ids['project_code']);x=s.get(base+'/workflow-instances',params={'pageNo':1,'pageSize':10},timeout=15).json();out={'workflow_list':x};print('WORKFLOW',[(r['id'],r['state']) for r in x['data']['totalList']],flush=True)
for r in x['data']['totalList']:
 tasks=s.get(base+f'/workflow-instances/{r["id"]}/tasks',timeout=15).json();out['tasks_'+str(r['id'])]=tasks;print('TASKS',[(t['name'],t['state']) for t in tasks['data']['taskList']],flush=True)
for engine,port,password in [('mo',6001,'111'),('mysql',13306,'types-local')]:
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,database='orchestrator10000',autocommit=True)
 with d.cursor() as c:
  c.execute('SELECT tag,rows_seen,sum_rev FROM ds_native_sql_audit');actual=c.fetchall();c.execute('SELECT COUNT(*),SUM(rev) FROM dolphinscheduler_decimal38_18');expected=c.fetchone();print(engine,'SQL',actual,'EXPECTED',expected,flush=True);out[engine]={'actual':actual,'expected':expected,'status':'passed' if len(actual)==1 and tuple(actual[0][1:])==expected else 'failed'}
 d.close()
(B/'dolphin-native-sql-result.json').write_text(json.dumps(out,indent=2,default=str))
