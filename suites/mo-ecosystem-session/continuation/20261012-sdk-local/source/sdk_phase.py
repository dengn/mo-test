import os,sys,json,pathlib,traceback,datetime,importlib.metadata
B=pathlib.Path(__file__).resolve().parent;P=B/'fivetran-project';sys.path.insert(0,str(P));os.chdir(P)
os.environ['PATH']='/workspace/work/etl-orchestrators-10000/fivetran-venv/bin:'+os.environ['PATH']
import fivetran_connector_sdk as sdk
from fivetran_connector_sdk import connector_helper as ch
C=pathlib.Path('/workspace/work/etl-orchestrators-10000/sdk-cache/tester')
assert (C/'version.txt').read_text().strip()==ch.TESTER_VERSION
# Reuse the already installed official tester/JDK read-only; all new SDK
# config, log, state and warehouse writes are confined to this new /tmp run.
ch.config_root_dir_helper=lambda:str(B/'sdk-config');sdk.ensure_tester_installed=lambda:(str(C/'bin/java'),str(C))
from connector import connector
phase=sys.argv[1];sf=P/'files/state.json';state=json.loads(sf.read_text()) if sf.exists() else {}
if phase=='evolve':state={'next_case':0,'phase':'evolve'}
config={'phase':'evolve' if phase=='evolve' or (phase=='noop' and state.get('phase')=='evolve') else 'base','inject':'true' if phase=='injected' else 'false'}
out={'phase':phase,'initial_state':state,'configuration':config,'SDK':importlib.metadata.version('fivetran-connector-sdk'),'scope':'Official local SDK/tester; archived MO/MySQL source provenance; canonical STRING envelope; no SaaS/native MO destination or main5000 certification','UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:connector.debug(project_path=str(P),configuration=config,state=state);out['returned']='normally'
except Exception as e:out.update(returned='exception',error=repr(e),traceback=traceback.format_exc())
out['durable_state']=json.loads(sf.read_text()) if sf.exists() else None;(B/f'phase-{phase}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('PHASE_RECEIPT',json.dumps(out,ensure_ascii=False),flush=True)
