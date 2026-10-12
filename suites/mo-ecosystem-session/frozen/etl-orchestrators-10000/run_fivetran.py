import pathlib,sys,json,os,datetime,traceback
B=pathlib.Path(__file__).resolve().parent;P=B/'fivetran-project';sys.path.insert(0,str(P));os.chdir(P)
os.environ['PATH']=str(B/'fivetran-venv/bin')+':'+os.environ['PATH']
from fivetran_connector_sdk import connector_helper as ch
ch.config_root_dir_helper=lambda:str(B/'sdk-cache')
from connector import connector
statefile=P/'files/state.json';receipts=[]
for phase in ['injected_failure','checkpoint_resume','state_noop']:
 state=json.loads(statefile.read_text()) if statefile.exists() else {};out={'phase':phase,'initial_state':state,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:connector.debug(project_path=str(P),configuration={'inject_once':'true'},state=state);out['returned']='normally'
 except Exception as e:out.update(returned='exception',error=repr(e));traceback.print_exc()
 out['durable_state']=json.loads(statefile.read_text()) if statefile.exists() else None;receipts.append(out);(B/'fivetran-debug-receipts.json').write_text(json.dumps(receipts,indent=2));print('PHASE',out,flush=True)
