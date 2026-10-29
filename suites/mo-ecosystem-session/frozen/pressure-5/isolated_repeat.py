from runtime import *
import mixed_load as m
for cn in ['stress5-pg','stress5-mo','stress5-mysql']:
 api('PUT','/connectors/'+cn+'/pause');poll(lambda:all(t['state']=='PAUSED' for t in api('GET','/connectors/'+cn+'/status')['tasks']),30)
dump0=m.dump
def save(path,value):
 if Path(path).name=='mixed-load-result.json':path=B/'mixed-isolated-repeat-result.json'
 return dump0(path,value)
m.dump=save;m.out={'runtime_ref':REF,'scope':'isolated repeat after CDC drain: no active arrival producer or hotspot writer, all CDC connectors paused; same 1M table and 4 CPU shared host; warm caches; checks every query and final writer state','stages':[]}
for w,r in [(4,0),(4,2)]:sql('TRUNCATE TABLE writer_state');m.run_stage(w,r)
print('ISOLATED REPEAT COMPLETE',flush=True)
