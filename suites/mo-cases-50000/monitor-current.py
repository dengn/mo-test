import time,json,os,shutil
from pathlib import Path
P=Path('/workspace/mo-cases-50000');start=time.time()
with (P/'resources-current.jsonl').open('a') as f:
 while not (P/'monitor-current.stop').exists():
  r={'epoch':time.time(),'memory_bytes':int(Path('/sys/fs/cgroup/memory.current').read_text()),'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),'disk_free':shutil.disk_usage('/workspace').free,'server_pid':Path('/workspace/mo-stress/server.pid').read_text().strip()}
  pid=r['server_pid'];r['server_alive']=Path('/proc/'+pid).exists();f.write(json.dumps(r)+'\n');f.flush();time.sleep(5)
