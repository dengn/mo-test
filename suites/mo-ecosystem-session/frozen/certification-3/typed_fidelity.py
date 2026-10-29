from runtime import *
import hashlib
out={'runtime_ref':REF,'scope':'exact typed source-target comparison for throughput burst and rate staircase; immutable independent ID ranges','cases':[]}
for route,low,count,kind in [('kafka',1000000,1000,'burst'),('nifi',100000,500,'burst'),('kafka',2100000,3000,'50/s'),('kafka',2120000,6000,'100/s'),('kafka',2140000,12000,'200/s'),('nifi',210000,1500,'25/s'),('nifi',215000,3000,'50/s')]:
 database='cert3' if route=='kafka' else 'runtime_ecosystem';st='records' if route=='kafka' else 'nifi_source';tt='records' if route=='kafka' else 'nifi_outbox_target';cols='id,'+('s,' if route=='nifi' else '')+'u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,'+('updated' if route=='nifi' else 'produced_ms')
 def get(p,t):
  rr=sql(p,database,'SELECT '+cols+' FROM '+t+' WHERE id>=%s AND id<%s ORDER BY id',(low,low+count))
  return [tuple(json.loads(v) if i==len(row)-2 and v is not None else v for i,v in enumerate(row)) for row in rr]
 s=get(13306,st);t=get(6001,tt);r={'route':route,'stage':kind,'low_id':low,'expected_count':count,'source_rows':len(s),'target_rows':len(t),'all_fields_equal':s==t,'distinct_target_ids':len({r[0] for r in t}),'source_sha256':hashlib.sha256(json.dumps(s,ensure_ascii=False,default=str).encode()).hexdigest(),'target_sha256':hashlib.sha256(json.dumps(t,ensure_ascii=False,default=str).encode()).hexdigest()};r['status']='passed' if s==t and len(s)==count else 'failed';out['cases'].append(r);print(json.dumps(r),flush=True)
dump(B/'typed-fidelity-result.json',out)
