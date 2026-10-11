import json,time,os,signal,shutil,urllib.request
from pathlib import Path
p=Path('/workspace/mo-vector-fulltext');previous={};ticks=os.sysconf('SC_CLK_TCK')
with open(p/'resources.jsonl','a',buffering=1) as f:
 while not (p/'monitor.stop').exists():
  now=time.time();v={'epoch':now,'memory_bytes':int(Path('/sys/fs/cgroup/memory.current').read_text()),'disk_free_bytes':shutil.disk_usage('/workspace').free,'memory_events':Path('/sys/fs/cgroup/memory.events').read_text().strip()}
  for label,path in [('server','/workspace/mo-stress/server.pid'),('client',str(p/'load.pid'))]:
   try:
    pid=int(Path(path).read_text());s=Path(f'/proc/{pid}/stat').read_text().split();cpu=(int(s[13])+int(s[14]))/ticks;v[label]={'pid':pid,'state':s[2],'rss_bytes':int(s[23])*os.sysconf('SC_PAGE_SIZE'),'cpu_seconds':cpu,'threads':int(s[19]),'fds':None}
    if label in previous and previous[label][0]==pid:v[label]['cpu_cores']=(cpu-previous[label][1])/(now-previous[label][2])
    try:v[label]['fds']=len(list(Path(f'/proc/{pid}/fd').iterdir()))
    except PermissionError:v[label]['fds_permission_denied']=True
    previous[label]=(pid,cpu,now)
   except Exception as e:v[label]={'unavailable':str(e)}
  try:
   body=urllib.request.urlopen('http://127.0.0.1:7001/metrics',timeout=2).read().decode();metrics={}
   for line in body.splitlines():
    if line.startswith(('go_goroutines ','go_memstats_heap_alloc_bytes ','go_memstats_heap_inuse_bytes ','process_open_fds ')):
     name,value=line.split();metrics[name]=float(value)
   v['metrics']=metrics
  except Exception as e:v['metrics_error']=str(e)
  if v['memory_bytes']>30*1024**3 or v['disk_free_bytes']<3*1024**3:
   v['resource_guard']=True
   try:os.kill(int((p/'load.pid').read_text()),signal.SIGTERM)
   except ProcessLookupError:pass
  f.write(json.dumps(v)+'\n');time.sleep(5)
