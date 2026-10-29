"""Create a private native Rill project, ingest from MO and query real metrics."""
import hashlib,json,os,socket,subprocess,time,uuid
from pathlib import Path
import common as c

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def run(state,config,limit):
    import native
    binary=Path(config['binary'])
    if not config.get('sha256') or hashlib.sha256(binary.read_bytes()).hexdigest()!=config['sha256']:raise native.NativeError('Rill binary identity mismatch')
    version=subprocess.run([str(binary),'version'],capture_output=True,text=True,timeout=30,check=True).stdout
    if 'v0.90.5' not in version:raise native.NativeError('Rill runtime version mismatch')
    private=c.ROOT/'runtime'/state['run_id']/('rill-'+uuid.uuid4().hex[:12]);private.mkdir(parents=True,mode=0o700,exist_ok=False)
    for folder in ['connectors','models','metrics']:(private/folder).mkdir(mode=0o700)
    def save(path,data):
        target=private/path;target.write_text(json.dumps(data,ensure_ascii=False,indent=2));target.chmod(0o600)
    save('rill.yaml',{'compiler':'rillv1'})
    creds=native.credentials(state,config)
    save('connectors/mysql.yaml',{'type':'connector','driver':'mysql',**creds,'ssl-mode':config.get('ssl_mode','DISABLED')})
    for domain in ['commerce','saas','marketing','finance','inventory','telemetry','support','workforce','supply','experiments']:
        name=domain+'_fact'
        save('models/'+name+'.yaml',{'type':'model','connector':'mysql','sql':'SELECT * FROM '+c.identifier(state['schemas']['semantic'])+'.'+c.identifier(name)})
        save('metrics/'+name+'_metrics.yaml',{'type':'metrics_view','model':name,'timeseries':'event_time',
          'dimensions':[{'name':n,'column':n} for n in ['scenario_id','category','state','channel','region','entity_id']],
          'measures':[{'name':name,'expression':sql} for name,sql in [('events','COUNT(*)'),('gross','SUM(amount)'),('net','SUM(net_amount)'),('adjustment','SUM(adjustment)'),('entities','COUNT(DISTINCT entity_id)'),('units','SUM(quantity)'),('average_latency','AVG(duration_ms)'),('weighted_value','SUM(amount)/NULLIF(SUM(quantity),0)')]]})
    http,grpc=port(),port()
    with (private/'rill.log').open('w') as log:
        proc=subprocess.Popen([str(binary),'start',str(private),'--no-open','--no-ui','--port',str(http),'--port-grpc',str(grpc),'--pull-env=false'],stdout=log,stderr=subprocess.STDOUT)
    api=native.HTTP({'url':'http://127.0.0.1:'+str(http),'timeout':120})
    all_cases=list(c.corpus('rill-metrics'))
    probes={}
    for case in all_cases:probes.setdefault(case['domain'],case)
    try:
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            if proc.poll() is not None:raise native.NativeError('Rill exited before ingestion completed')
            try:
                resources=api.get('/v1/instances/default/resources')
                # Runtime reconciliation is asynchronous; a real metric request
                # proves that the connector/model/metric resources are usable.
                for domain,first in probes.items():
                    api.call('/v1/instances/default/queries/metrics-views/'+domain+'_fact_metrics/aggregation',first['request'])
                break
            except Exception:time.sleep(.5)
        else:raise native.NativeError('Rill ingestion/readiness timeout')
        cases=all_cases[:limit] if limit else all_cases
        for case in cases:
            started=time.monotonic();query=case['request'];keys=[x['name'] for x in query['dimensions']+query['measures']]
            try:
                body=api.call('/v1/instances/default/queries/metrics-views/'+case['domain']+'_fact_metrics/aggregation',query)
                rows=[[r.get(k) for k in keys] for r in body['data']]
                result=c.record(case,rows,version='0.90.5',path='native-metrics-local-duckdb',elapsed_seconds=round(time.monotonic()-started,6))
                if result['status']=='mismatch' and native.known_client_value('rill',case,rows,state):
                    result.update(status='known_failure',failure_kind='client_precision_loss',independent_source_control='passed')
                yield result
            except Exception as e:yield {'id':case['id'],'status':'error','error':native.protect_error(e,config)}
    finally:
        proc.terminate()
        try:proc.wait(timeout=20)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
