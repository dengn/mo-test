"""Run the official Redash MySQL runner and its production JSON encoder."""
import importlib.metadata,json,sys
from pathlib import Path
sys.path.insert(0,'/app')
from redash.query_runner.mysql import Mysql
from redash.utils import json_dumps,json_loads
import redash

input_path,output_path=map(Path,sys.argv[1:3]);config=json.loads(input_path.read_text())
version=redash.__version__
assert version==config['version'], 'Redash package version mismatch'
assert importlib.metadata.version('mysqlclient')=='2.1.1','Redash bundled driver mismatch'
creds=config['credentials'];runner=Mysql({'host':creds['host'],'port':creds['port'],'db':creds['database'],
 'user':creds['user'],'passwd':creds['password'],'use_ssl':config['ssl']})
records=[]
for case in config['cases']:
    try:
        result,error=runner.run_query(case['sql'],None)
        if error:raise RuntimeError(error)
        serialized=json_loads(json_dumps(result)) if isinstance(result,dict) else json_loads(result)
        keys=[x['name'] for x in serialized['columns']]
        records.append({'id':case['id'],'rows':[[row[k] for k in keys] for row in serialized['rows']]})
    except Exception as exc:records.append({'id':case['id'],'error':str(exc)})
output_path.write_text(json.dumps({'version':version,'records':records}))
