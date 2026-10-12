from common import *
BASE='http://127.0.0.1:10088/nifi-api';I=json.loads((B/'nifi-ids.json').read_text());out=json.loads((B/'nifi-expanded-result.json').read_text());N='runtime_ecosystem'
conn=I['connections']['retained-rejects'];q=I['processors']['QueryDatabaseTableRecord']
sql(13306,N,'INSERT INTO nifi_outbox(sqltext) VALUES(%s)',("UPDATE nifi_outbox_target SET name='"+'x'*301+"' WHERE id=1",))
maxseq=sql(13306,N,'SELECT MAX(seq) FROM nifi_outbox')[0][0]
poll(lambda:api('GET','/connections/'+conn,base=BASE)['status']['aggregateSnapshot']['flowFilesQueued']==1,50)
state=api('GET','/processors/'+q+'/state',base=BASE)['componentState']['localState']['state']
case={'name':'invalid-long-string-retained-reject-not-silent-loss','status':'passed','injected_seq':maxseq,'checkpoint':state,'retained_rejects':1,'source_row':sql(13306,N,'SELECT id,name,updated FROM nifi_source WHERE id=1'),'target_row':sql(6001,N,'SELECT id,name,updated FROM nifi_outbox_target WHERE id=1'),'bulletins':api('GET','/flow/bulletin-board',base=BASE)}
case['status']='passed' if case['source_row']==case['target_row'] and int(state[0]['value'])>=maxseq else 'failed';out['cases'].append(case);out['retained_rejects']=1;dump(B/'nifi-expanded-result.json',out);print(case['name'],case['status'],flush=True)
# Keep the deliberately rejected event in its stopped retention queue for inspection.
