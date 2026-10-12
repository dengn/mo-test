from runtime import *
import threading,shutil,hashlib,traceback
duration=int(os.environ.get('CERT3_SOAK_SECONDS','1800'));begin=time.monotonic();epoch=time.time();stop=threading.Event();generation_stop=threading.Event();lock=threading.Lock();last_seen={'kafka':set(),'nifi':set()};lat={'kafka':[],'nifi':[]};generated={'kafka':0,'nifi':0};source_lat={'kafka':[],'nifi':[]};errors=[];faults=[];recoveries=[];minute=[];expected_deletes={'kafka':set(),'nifi':set()};start_ids={'kafka':3000000,'nifi':300000};frontier=start_ids.copy();I=json.loads((B/'nifi-ids.json').read_text());NIFI='http://127.0.0.1:10088/nifi-api'
out={'runtime_ref':REF,'planned_duration_s':duration,'scope':'single-node shared 4 CPU quota; moderate fixed rate Kafka 10 insert/s, NiFi 5 insert/s plus one update/delete per route per minute; polling-visible latency, not intrinsic per-query latency','started_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_errors':errors,'faults':faults,'controlled_task_restarts':recoveries,'minutes':minute,'status':'running'}
def save():
 out['elapsed_s']=round(time.monotonic()-begin,2);out['generated']=generated.copy();out['observed_inserts']={k:len(v) for k,v in last_seen.items()};dump(B/'soak-progress.json',out)
def producer():
 tick=0
 while not stop.is_set() and not generation_stop.is_set() and time.monotonic()-begin<duration:
  due=begin+tick;stop.wait(max(0,due-time.monotonic()))
  for route,rate in [('kafka',10),('nifi',5)]:
   base=start_ids[route];table='records' if route=='kafka' else 'nifi_source';database='cert3' if route=='kafka' else 'runtime_ecosystem';now=int(time.time()*1000);j=generated[route]
   try:
    if route=='kafka':
     values=[(base+j+i,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','持续😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',now) for i in range(rate)];stmt='INSERT INTO records VALUES('+','.join(['%s']*8)+')'
    else:
     values=[(base+j+i,2**63-1,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','持续😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',now) for i in range(rate)];stmt='INSERT INTO nifi_source(id,s,u,d,payload,name,ts,doc,updated) VALUES('+','.join(['%s']*9)+')'
    t=time.monotonic()
    with db(13306,database) as d,d.cursor() as c:c.executemany(stmt,values)
    source_lat[route].append((time.monotonic()-t)*1000);generated[route]+=rate
    if tick and tick%60==0:
     delete_id=base+(tick-30)*rate;update_id=base+(tick-20)*rate
     sql(13306,database,'DELETE FROM '+table+' WHERE id=%s',(delete_id,));expected_deletes[route].add(delete_id)
     sql(13306,database,'UPDATE '+table+" SET name='持续更新😀',ts='2026-10-11 12:00:00.654321' WHERE id=%s",(update_id,))
   except Exception as e:errors.append({'elapsed_s':time.monotonic()-begin,'route':route,'error':str(e),'uncertain_source_commit':'no blind replay; final source-target comparison required'})
  tick+=1
def monitor():
 while not stop.is_set():
  for route in ['kafka','nifi']:
   if not generated[route]:continue
   try:
    database='cert3' if route=='kafka' else 'runtime_ecosystem';table='records' if route=='kafka' else 'nifi_outbox_target';stamp='produced_ms' if route=='kafka' else 'updated';base=start_ids[route];seen=last_seen[route]
    low=frontier[route]
    while low in seen or low in expected_deletes[route]:low+=1
    frontier[route]=low
    rr=sql(6001,database,'SELECT id,'+stamp+' FROM '+table+' WHERE id>=%s ORDER BY id',(low,));now=time.time()*1000
    for id,ts in rr:
     if id not in seen:seen.add(id);lat[route].append({'id':id,'ms':max(0,now-ts),'elapsed_s':time.monotonic()-begin})
   except Exception as e:
    # Availability failures are counted separately from generator/source commit errors.
    with (B/'monitor-errors.jsonl').open('a') as f:f.write(json.dumps({'elapsed_s':time.monotonic()-begin,'route':route,'error':str(e)},ensure_ascii=False)+'\n')
  stop.wait(.5)
def controller():
 planned=[(180,'connect','org.apache.kafka.connect.cli.ConnectDistributed'),(600,'mo','/workspace/matrixone/mo-service'),(1200,'nifi','org.apache.nifi.NiFi')];done=set()
 while not stop.is_set():
  elapsed=time.monotonic()-begin
  for at,name,marker in planned:
   if elapsed>=at and name not in done:
    done.add(name)
    try:
     f=kill(name,marker);f['elapsed_s']=elapsed;faults.append(f);save();stop.wait(3);start(name)
    except Exception as e:errors.append({'phase':'fault-controller','service':name,'error':str(e)})
  try:
   if sql(6001,None,'SELECT 1'):
    for n in ['cert3-source','cert3-sink']:
     s=api('GET','/connectors/'+n+'/status')
     if any(t['state']=='FAILED' for t in s.get('tasks',[])):
      api('POST','/connectors/'+n+'/restart?includeTasks=true&onlyFailed=true');recoveries.append({'connector':n,'elapsed_s':elapsed,'reason':'FAILED task; controlled restart, not native automatic recovery'});save()
  except Exception:pass
  stop.wait(5)
threads=[threading.Thread(target=f,daemon=True) for f in [producer,monitor,controller]]
for t in threads:t.start()
last_cpu=int(Path('/sys/fs/cgroup/cpu.stat').read_text().split('usage_usec ')[1].splitlines()[0]);last_t=time.monotonic();last_counts={'kafka':0,'nifi':0};lat_cursor={'kafka':0,'nifi':0}
try:
 while time.monotonic()-begin<duration:
  stop.wait(min(30,max(0,duration-(time.monotonic()-begin))));now=time.monotonic();cpu=int(Path('/sys/fs/cgroup/cpu.stat').read_text().split('usage_usec ')[1].splitlines()[0]);rss={}
  for n in ['mo','kafka','connect','nifi']:
   try:rss[n]=int(Path('/proc',str(int((B/(n+'.pid')).read_text())),'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')/1048576
   except Exception:rss[n]=None
  sample={'elapsed_s':round(now-begin,2),'cpu_quota_utilization_percent':(cpu-last_cpu)/((now-last_t)*4*1e6)*100,'rss_MB':rss,'free_disk_MB':shutil.disk_usage(B).free/1048576,'routes':{}}
  for route in ['kafka','nifi']:
   values=[x['ms'] for x in lat[route][lat_cursor[route]:]];lat_cursor[route]=len(lat[route]);seen=len(last_seen[route]);sample['routes'][route]={'generated':generated[route],'first_visible':seen,'visible_rows_per_s':(seen-last_counts[route])/(now-last_t),'unobserved_inserts':generated[route]-seen,'window_latency_ms_p50':percentile(values,.5),'window_latency_ms_p95':percentile(values,.95),'window_latency_ms_p99':percentile(values,.99)};last_counts[route]=seen
  try:sample['connector_status']={n:api('GET','/connectors/'+n+'/status') for n in ['cert3-source','cert3-sink']}
  except Exception as e:sample['connector_status_error']=str(e)
  minute.append(sample);last_cpu=cpu;last_t=now;save();print('PROGRESS',json.dumps(sample,ensure_ascii=False),flush=True)
  if sample['free_disk_MB']<650:out['status']='stopped_by_disk_guard';break
finally:
 # Stop generation, then allow the existing pipelines to drain before stopping monitor/controller.
 out['load_end_elapsed_s']=time.monotonic()-begin;generation_stop.set()
 for t in [threads[0]]:t.join(timeout=2)
 drain_begin=time.monotonic();equal=False;final={}
 while time.monotonic()-drain_begin<180:
  try:
   final={}
   for route in ['kafka','nifi']:
    database='cert3' if route=='kafka' else 'runtime_ecosystem';st='records' if route=='kafka' else 'nifi_source';tt='records' if route=='kafka' else 'nifi_outbox_target';cols='id,'+('s,' if route=='nifi' else '')+'u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,'+('updated' if route=='nifi' else 'produced_ms');base=start_ids[route]
    expected=sql(13306,database,'SELECT '+cols+' FROM '+st+' WHERE id>=%s ORDER BY id',(base,));actual=sql(6001,database,'SELECT '+cols+' FROM '+tt+' WHERE id>=%s ORDER BY id',(base,))
    def normalize(rr):return [tuple(json.loads(v) if i==len(row)-2 and v is not None else v for i,v in enumerate(row)) for row in rr]
    final[route]={'source_rows':len(expected),'target_rows':len(actual),'all_fields_equal':normalize(expected)==normalize(actual),'source_sha256':hashlib.sha256(json.dumps(normalize(expected),ensure_ascii=False,default=str).encode()).hexdigest(),'target_sha256':hashlib.sha256(json.dumps(normalize(actual),ensure_ascii=False,default=str).encode()).hexdigest(),'pk_count':sql(6001,database,'SELECT COUNT(*),COUNT(DISTINCT id) FROM '+tt+' WHERE id>=%s',(base,)),'intentional_source_deletes':len(expected_deletes[route])}
   equal=all(r['all_fields_equal'] for r in final.values())
   if equal:break
  except Exception as e:out['drain_error']=str(e)
  time.sleep(2)
 stop.set()
 for t in threads:t.join(timeout=3)
 out['drain_s']=time.monotonic()-drain_begin;out['final']=final;out['latency']={k:{'samples':len(v),'ms_p50':percentile([x['ms'] for x in v],.5),'ms_p95':percentile([x['ms'] for x in v],.95),'ms_p99':percentile([x['ms'] for x in v],.99),'ms_max':max([x['ms'] for x in v],default=None)} for k,v in lat.items()};out['source_commit_ms']={k:{'samples':len(v),'p50':percentile(v,.5),'p95':percentile(v,.95),'p99':percentile(v,.99)} for k,v in source_lat.items()}
 if out['status']=='running':out['status']='passed_observed_30min_scope' if equal and not errors and out['load_end_elapsed_s']>=duration else 'failed'
 dump(B/'soak-result.json',out);dump(B/'soak-latency-samples.json',lat);save();print('SOAK COMPLETE',out['status'],flush=True)
