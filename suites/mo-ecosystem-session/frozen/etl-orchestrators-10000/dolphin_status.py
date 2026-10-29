import pathlib,json,requests
B=pathlib.Path(__file__).resolve().parent;ids=json.loads((B/'dolphin-runtime-ids.json').read_text());s=requests.Session();s.headers['sessionId']=(B/'dolphin-session').read_text();base='http://127.0.0.1:12345/dolphinscheduler/projects/'+str(ids['project_code']);x=s.get(base+'/workflow-instances',params={'pageNo':1,'pageSize':10},timeout=20).json();out={'workflow_list':x};print('workflow states',[(r['id'],r['state']) for r in x['data']['totalList']],flush=True)
for r in x['data']['totalList']:
 tasks=s.get(base+f'/workflow-instances/{r["id"]}/tasks',timeout=20).json();out['tasks_'+str(r['id'])]=tasks;print('tasks',[(t['name'],t['state'],t.get('retryTimes')) for t in tasks['data']['taskList']],flush=True)
(B/'dolphin-final-status.json').write_text(json.dumps(out,indent=2))
