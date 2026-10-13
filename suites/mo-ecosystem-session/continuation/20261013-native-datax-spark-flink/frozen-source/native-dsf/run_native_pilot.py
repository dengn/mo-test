import sys,os,runpy
from pathlib import Path
B=Path('/tmp/mo-heavy-alternative-20261012');D=Path(__file__).parent
sys.path.insert(0,'/workspace/toolchains/python/lib/python3.12/site-packages');sys.path.insert(0,str(B/'windowed'));sys.path.insert(0,str(D))
import json
inventory=D/'java-runtime-inventory.json'
route=sys.argv[sys.argv.index('--route')+1]
if inventory.exists() and route in ['spark','dataxjava8']:
 home=json.loads(inventory.read_text()).get('jre8' if route=='dataxjava8' else 'jre17',{}).get('home')
 if home:os.environ['JAVA_HOME']=home;os.environ['PATH']=home+'/bin:'+os.environ['PATH']
import guard_5g;guard_5g.install()
import driver_routes,native_iceberg,native_airflow,native_batch
native_batch.install()
try:runpy.run_path(str(D/'run_windows_preserved.py'),run_name='__main__')
finally:
 if native_batch.SPARK is not None:native_batch.SPARK.stop()
