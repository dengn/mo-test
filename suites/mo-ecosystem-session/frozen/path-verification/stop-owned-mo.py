import subprocess,os,signal
from pathlib import Path
ps=subprocess.run(['pgrep','-x','mo-service'],capture_output=True,text=True)
owned=[]
for pid in ps.stdout.split():
 cmd=Path('/proc/'+pid+'/cmdline').read_bytes().split(b'\0')
 if b'/workspace/work/path-verification/runtime/mo-config/launch.toml' in cmd or b'/workspace/work/path-verification/runtime/mo-config/launch-tls.toml' in cmd:owned.append(int(pid))
assert len(owned)==1,owned
os.kill(owned[0],signal.SIGTERM);print('SIGTERM sent to owned test service',owned[0])
