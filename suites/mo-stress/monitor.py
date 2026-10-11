import json,time,os,signal,shutil
from pathlib import Path
root=Path('/workspace/mo-stress');pid=int((root/'server.pid').read_text());ticks=os.sysconf('SC_CLK_TCK');previous=None
with open(root/'resources.jsonl','a',buffering=1) as out:
 while not (root/'monitor.stop').exists():
  row={'time_epoch':time.time()}
  try:
   stat=Path(f'/proc/{pid}/stat').read_text().split();row.update(server_cpu_seconds=(int(stat[13])+int(stat[14]))/ticks,server_rss_bytes=int(stat[23])*os.sysconf('SC_PAGE_SIZE'),server_threads=int(stat[19]),server_state=stat[2])
   if previous:row['server_cpu_cores']=(row['server_cpu_seconds']-previous['server_cpu_seconds'])/(row['time_epoch']-previous['time_epoch'])
   previous=row.copy()
  except Exception as e:row['server_unavailable']=str(e)
  row['cgroup_memory_bytes']=int(Path('/sys/fs/cgroup/memory.current').read_text());row['disk_free_bytes']=shutil.disk_usage('/workspace').free
  row['memory_events']=Path('/sys/fs/cgroup/memory.events').read_text().strip()
  if row['disk_free_bytes']<3*1024**3 or row['cgroup_memory_bytes']>30*1024**3:
   row['guard_triggered']=True
   p=root/'load.pid'
   if p.exists():
    try:os.kill(int(p.read_text()),signal.SIGTERM)
    except ProcessLookupError:pass
  out.write(json.dumps(row)+'\n');time.sleep(5)
