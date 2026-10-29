from pathlib import Path
import json,inspect,hashlib,os
APP=Path(__file__).parent/'capacity-approval-6g.json'
def install():
 import runtime
 approved=json.loads(APP.read_text());assert approved['approved'] is True and approved['max_used_bytes']==6*1024**3
 assert os.environ['MO_TEST_DATABASE']=='mo_ecosystem_heavy_20261012'
 assert os.environ['MO_CASE_MIN_FREE_MIB']=='2048'
 source=inspect.getsource(runtime.guard);assert source.count('4*1024**3')==1
 patched=source.replace('4*1024**3','6*1024**3').replace('usage exceeds4GiB','usage exceeds6GiB')
 exec(compile(patched,str(APP),'exec'),runtime.__dict__)
 return runtime
