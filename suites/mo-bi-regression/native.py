"""Actual BI HTTP/SDK adapters. No SQL replay is labelled a native BI test."""
import base64,copy,gzip,json,os,re,socket,subprocess,sys,time,uuid
from pathlib import Path
from urllib.parse import quote,urlsplit
import requests
import common as c

VERSIONS={'metabase':'v0.64.1.5','superset':'6.1.0','grafana':'13.2.3','redash':'26.9.0',
 'dataease':'2.10.17','evidence':'1.1.6','rill':'0.90.5','zeppelin':'0.12.0','sqlpad':'7.5.7','lightdash':'2.573.1'}

class NativeError(RuntimeError):pass

def load_config(path):
    return json.loads(Path(path).read_text())

def resolve_config(config):
    options=copy.deepcopy(config)
    for field in ('username','password','token'):
        key=field+'_env'
        if key in options:options[field]=os.environ[options[key]]
    return options

def known_client_value(tool,case,rows,state):
    """A failed independent comparison remains failed. Only identify an exact
    historical client failure fingerprint after a current source-SQL control."""
    with gzip.open(c.ROOT/'corpus/known-client-values.json.gz','rt') as f:old=json.load(f).get(tool,{}).get(case['id'])
    if not old:return False
    historical=case|{'expected':old['actual']}
    if c.compare(rows,historical):return False
    if tool=='rill':
        expressions={'events':'COUNT(*)','gross':'SUM(amount)','net':'SUM(net_amount)','adjustment':'SUM(adjustment)','entities':'COUNT(DISTINCT entity_id)','units':'SUM(quantity)','weighted_value':'SUM(amount)/NULLIF(SUM(quantity),0)'}
        query=case['request'];dims=[x['name'] for x in query['dimensions']]
        names=dims+[expressions[x['name']] for x in query['measures']]
        sql='SELECT '+','.join(names)+' FROM '+c.identifier(state['schemas']['semantic'])+'.'+c.identifier(case['domain']+'_fact')+' WHERE '+query['whereSql']
        if dims:sql+=' GROUP BY '+','.join(dims)+' ORDER BY '+','.join(dims)
    else:sql=c.remap(case['sql'],state)
    with c.connection(state['schemas']['baseline']) as cx,cx.cursor() as q:q.execute(sql);source=q.fetchall()
    return c.compare(source,case) is None

def protect_error(exc,config):
    error=c.safe_error(exc)
    for key,value in (config or {}).items():
        if any(k in key.lower() for k in ('password','token','secret')) and isinstance(value,str) and value:
            error['message']=error['message'].replace(value,'[redacted]')
    return error

class HTTP:
    def __init__(self,config):
        self.config=config;self.base=config['url'].rstrip('/');self.s=requests.Session()
        # Loopback is an owned local service; other addresses retain the proxy.
        if urlsplit(self.base).hostname in ('localhost','127.0.0.1','::1'):self.s.trust_env=False
        if config.get('ca_file'):self.s.verify=config['ca_file']
        if config.get('token'):self.s.headers['Authorization']='Bearer '+config['token']
    def call(self,path,data=None,method='post'):
        r=self.s.request(method,self.base+path,json=data,timeout=self.config.get('timeout',120))
        try:body=json.loads(r.text,parse_float=c.D)
        except ValueError:raise NativeError('Non-JSON response at '+path)
        if not r.ok:
            diagnostic={k:body[k] for k in ('message','error','errors') if k in body}
            if isinstance(body.get('details'),dict) and body['details'].get('verboseMessage'):
                diagnostic['verboseMessage']=body['details']['verboseMessage']
            text=str(diagnostic or body)
            if len(text)>2400:text=text[:400]+' ... '+text[-2000:]
            raise NativeError('HTTP '+str(r.status_code)+' '+text)
        return body
    def get(self,path):return self.call(path,method='get')

def credentials(state,config,db='baseline'):
    return {'host':config.get('database_host',os.getenv('MO_HOST','127.0.0.1')),'port':int(os.getenv('MO_PORT','6001')),
            'database':state['schemas'][db],'user':os.getenv('MO_USER','root'),'password':os.environ['MO_PASSWORD']}

def mb_remap(value,ids,database):
    if isinstance(value,list):return [mb_remap(v,ids,database) for v in value]
    if isinstance(value,dict):
        result={k:mb_remap(v,ids,database) for k,v in value.items()}
        if 'database' in result:result['database']=database
        if isinstance(result.get('source-table'),str) and result['source-table'].startswith('card__'):
            result['source-table']='card__'+str(ids[int(result['source-table'][6:])])
        return result
    return value

def metabase(state,config,limit):
    api=HTTP(config)
    if not config.get('token'):
        login=api.call('/api/session',{'username':config['username'],'password':config['password']})
        api.s.headers['X-Metabase-Session']=login['id'];api.s.headers.pop('Authorization',None)
    version=api.get('/api/session/properties')['version']['tag']
    if version!=VERSIONS['metabase']:raise NativeError('Metabase runtime version mismatch: '+str(version))
    creds=credentials(state,config,'core')
    did=api.call('/api/database',{'name':'mo-test-'+state['run_id'],'engine':'mysql','is_full_sync':False,
      'details':{'host':creds['host'],'port':creds['port'],'dbname':creds['database'],'user':creds['user'],'password':creds['password'],
      'ssl':config.get('ssl',False),'additional-options':config.get('additional_options','usePipelineAuth=false&useBatchMultiSend=false&useSsl=false')}})['id']
    ids={};models=json.loads((c.ROOT/'corpus/models.json').read_text())
    for name,model in models.items():
        card=api.call('/api/card',{'name':'mo-test '+state['run_id']+' '+name,'type':'model','display':'table','visualization_settings':{},
           'dataset_query':{'database':did,'type':'native','native':{'query':c.remap(model['sql'],state)}}})
        ids[model['id']]=card['id']
    cases=list(c.corpus('metabase'));selected=cases[:limit] if limit else cases
    for case in selected:
        started=time.monotonic()
        try:
            body=api.call('/api/dataset',mb_remap(case['query'],ids,did))
            if body.get('status')!='completed':raise NativeError(str(body.get('error','Incomplete Metabase query')))
            result=c.record(case,body['data']['rows'])
        except Exception as e:result={'id':case['id'],'status':'error','error':protect_error(e,config)}
        yield result|{'elapsed_seconds':round(time.monotonic()-started,6),'version':version,'path':'query-builder'}
    # Persist native metrics and a shared-filter dashboard, then execute saved
    # cards through the actual dashboard API rather than only /api/dataset.
    index={r['id']:r for r in cases};cards=[]
    for domain in range(1,11):
        case=index[f'BI-D{domain:02d}-P20-T02'];query=mb_remap(case['query'],ids,did)
        query['query']['aggregation']=query['query']['aggregation'][:1];query['query'].pop('filter',None)
        card=api.call('/api/card',{'name':'mo-test net metric '+str(domain)+' '+state['run_id'],'type':'metric','display':'scalar','visualization_settings':{},'dataset_query':query})
        read=api.get('/api/card/'+str(card['id']))
        yield {'id':f'SAVED-METRIC-{domain:02d}','status':'passed' if read['type']=='metric' and read['name']==card['name'] else 'mismatch','version':version,'path':'saved-metric'}
        cards.append(card['id'])
    dashboard=api.call('/api/dashboard',{'name':'mo-test metric dashboard '+state['run_id'],'parameters':[{'id':'scenario','name':'Scenario','slug':'scenario','type':'number/='}]})
    field=['field','scenario_id',{'base-type':'type/Integer'}]
    dashcards=[{'id':-(i+1),'card_id':card,'row':i//2*4,'col':i%2*12,'size_x':12,'size_y':4,
                'parameter_mappings':[{'parameter_id':'scenario','card_id':card,'target':['dimension',field]}],'visualization_settings':{}} for i,card in enumerate(cards)]
    dashboard=api.call('/api/dashboard/'+str(dashboard['id']),{'dashcards':dashcards},method='put')
    for di,dc in enumerate(dashboard['dashcards'],1):
        for sid in (1,61,91,101,191):
            pi=(sid-1)//10+1;case=copy.deepcopy(index[f'BI-D{di:02d}-P{pi:02d}-T02'])
            case['id']=f'DASHBOARD-D{di:02d}-S{sid:03d}';case['expected']=[[r[0]] for r in case['expected']]
            payload={'parameters':[{'id':'scenario','type':'number/=','value':[sid],'target':['dimension',field]}]}
            try:
                body=api.call(f'/api/dashboard/{dashboard["id"]}/dashcard/{dc["id"]}/card/{dc["card_id"]}/query',payload)
                if body.get('status')!='completed':raise NativeError(str(body.get('error')))
                yield c.record(case,body['data']['rows'],path='saved-dashboard-filter',version=version)
            except Exception as e:yield {'id':case['id'],'status':'error','error':protect_error(e,config)}

def http_queries(tool,state,config,cases):
    api=HTTP(config);creds=credentials(state,config);runtime_name='mo-test '+state['run_id']+' '+uuid.uuid4().hex[:8]
    if tool=='grafana':
        if config.get('username'):api.s.auth=(config['username'],config['password'])
        version=api.get('/api/health')['version']
        if version!=VERSIONS[tool]:raise NativeError('Grafana runtime version mismatch')
        ds=api.call('/api/datasources',{'name':runtime_name,'type':'mysql','access':'proxy','url':creds['host']+':'+str(creds['port']),
             'database':creds['database'],'user':creds['user'],'secureJsonData':{'password':creds['password']},'jsonData':config.get('json_data',{})})['datasource']['uid']
        try:
            health=api.get('/api/datasources/uid/'+ds+'/health')
            yield {'id':'DATASOURCE-HEALTH','status':'passed' if health.get('status')=='OK' else 'error','version':version,'path':'datasource-health'}
        except Exception as e:yield {'id':'DATASOURCE-HEALTH','status':'known_failure' if 'invalid connection' in str(e) else 'error','error':protect_error(e,config),'issue':'https://github.com/matrixorigin/matrixone/issues/29206'}
    elif tool=='sqlpad':
        api.call('/api/signin',{'email':config['username'],'password':config['password']})
        # SQLPad's app endpoint is exposed by the native server.
        version=api.get('/api/app')['version']
        if version!=VERSIONS[tool]:raise NativeError('SQLPad runtime version mismatch')
        ds=api.call('/api/connections',{'name':runtime_name,'driver':'mysql','host':creds['host'],'port':str(creds['port']),
          'database':creds['database'],'username':creds['user'],'password':creds['password']})['id']
    elif tool=='superset':
        login=api.call('/api/v1/security/login',{'username':config['username'],'password':config['password'],'provider':'db','refresh':True})
        api.s.headers['Authorization']='Bearer '+login['access_token']
        csrf=api.get('/api/v1/security/csrf_token/')
        if csrf.get('result'):api.s.headers['X-CSRFToken']=csrf['result']
        # Version contract is supplied by the launcher's official image identity;
        # Superset has no universally available unauthenticated version route.
        if config.get('version')!=VERSIONS[tool] or not config.get('image_digest'):raise NativeError('Pinned Superset image/version identity is required')
        version=config['version']
        uri=f'mysql+pymysql://{quote(creds["user"],safe="")}:{quote(creds["password"],safe="")}@{creds["host"]}:{creds["port"]}/{creds["database"]}?charset=utf8mb4'
        ds=api.call('/api/v1/database/',{'database_name':runtime_name,'sqlalchemy_uri':uri,'expose_in_sqllab':True,'allow_dml':False,'allow_run_async':False})['id']
    elif tool=='dataease':
        if config.get('version')!=VERSIONS[tool] or not config.get('release_sha256'):raise NativeError('Pinned DataEase release identity is required')
        if not config.get('release_file') or c.hashlib.sha256(Path(config['release_file']).read_bytes()).hexdigest()!=config['release_sha256']:raise NativeError('DataEase release hash mismatch')
        import zipfile
        with zipfile.ZipFile(config['release_file']) as jar:
            if 'Implementation-Version: '+VERSIONS[tool] not in jar.read('META-INF/MANIFEST.MF').decode():raise NativeError('DataEase native release version mismatch')
        creds=credentials(state,config,'semantic')
        version=config['version'];cfg={'host':creds['host'],'port':creds['port'],'dataBase':creds['database'],'username':creds['user'],'password':creds['password'],
         'urlType':'hostName','extraParams':config.get('extra_params','characterEncoding=UTF-8&connectTimeout=5000&useSSL=false&allowPublicKeyRetrieval=true&zeroDateTimeBehavior=convertToNull')}
        payload={'name':runtime_name,'type':'mysql','configuration':base64.b64encode(json.dumps(cfg).encode()).decode()}
        valid=api.call('/de2api/datasource/validate',payload)
        if valid.get('code')!=0:raise NativeError('DataEase datasource validation failed')
        saved=api.call('/de2api/datasource/save',payload)
        if saved.get('code')!=0 or not saved.get('data'):raise NativeError('DataEase datasource save failed: '+str(saved.get('msg')))
        ds=saved['data']['id']
        # Saving a datasource completes before the native connection pool is
        # ready. Probe the real preview path instead of treating that transient
        # deployment state as a failed analytical case.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            probe=api.call('/de2api/datasetData/previewSql',{'datasourceId':ds,'sql':base64.b64encode(b'SELECT 1 AS metric_value').decode(),'isCross':False})
            if probe.get('code')==0:break
            time.sleep(.2)
        else:raise NativeError('DataEase native preview readiness timeout')
        yield {'id':'SAVED-DATASOURCE','status':'passed','path':'saved-datasource','version':version,'datasource_id':ds,'default_schema':creds['database']}
    elif tool=='zeppelin':
        version=api.get('/api/version')['body']['version']
        if version!=VERSIONS[tool]:raise NativeError('Zeppelin runtime version mismatch')
        # User provisions a pinned JDBC interpreter against these fresh schemas.
        settings=api.get('/api/interpreter/setting')['body'];setting=next(x for x in settings if x['name']==config.get('interpreter','jdbc'))
        props=setting['properties'];values={'default.url':f'jdbc:mysql://{creds["host"]}:{creds["port"]}/{creds["database"]}?useSSL=false&connectionCollation=utf8mb4_general_ci&serverTimezone=UTC',
           'default.user':creds['user'],'default.password':creds['password'],'default.driver':'com.mysql.cj.jdbc.Driver','common.max_count':'100000','zeppelin.jdbc.maxRows':'100000'}
        for key,val in values.items():props[key]={'name':key,'value':val,'type':'string'}
        api.call('/api/interpreter/setting/'+setting['id'],{'name':setting['name'],'group':setting['group'],'properties':props,'dependencies':setting.get('dependencies',[]),'option':setting.get('option',{})},method='put')
        ds=api.call('/api/notebook',{'name':'mo-test '+state['run_id'],'defaultInterpreterGroup':'jdbc'})['body']
    else:raise ValueError(tool)
    for case in cases:
        started=time.monotonic();sql=c.remap(case['sql'],state)
        if tool=='dataease' and case['id'].startswith('BASE-'):
            sql=re.sub(r'\b(FROM|JOIN)\s+(customers|products|orders|refunds|events|edge_values|ledger)\b',
              lambda m:m[1]+' '+state['schemas']['baseline']+'.'+m[2],sql,flags=re.I)
        try:
            if tool=='grafana':
                body=api.call('/api/ds/query',{'from':'0','to':'9999999999999','queries':[{'refId':'A','datasource':{'type':'mysql','uid':ds},'rawSql':sql,'format':'table'}]})['results']['A']
                if body.get('error'):raise NativeError(body['error'])
                frames=body.get('frames',[])
                rows=[]
                for frame in frames:
                    columns=frame['data']['values'];fields=frame['schema']['fields']
                    converted=[]
                    for field,values in zip(fields,columns):
                        if field.get('type')=='time':
                            values=[c.datetime.datetime.fromtimestamp(float(v)/1000,c.datetime.timezone.utc) if v is not None else None for v in values]
                        converted.append(values)
                    rows.extend(map(list,zip(*converted)))
            elif tool=='superset':
                body=api.call('/api/v1/sqllab/execute/',{'database_id':ds,'schema':creds['database'],'sql':sql,'runAsync':False,'select_as_cta':False,'queryLimit':100000,'expand_data':True,'client_id':str(uuid.uuid4())})
                names=[x['name'] for x in body['columns']];rows=[[row[n] for n in names] for row in body['data']]
            elif tool=='dataease':
                body=api.call('/de2api/datasetData/previewSql',{'datasourceId':ds,'sql':base64.b64encode(sql.encode()).decode(),'isCross':False})
                if body.get('code')!=0:raise NativeError(str(body.get('msg')))
                data=body['data']['data'];names=[f['originName'] for f in data['fields']];rows=[[row[n] for n in names] for row in data['data']]
            elif tool=='sqlpad':
                batch=api.call('/api/batches',{'connectionId':ds,'batchText':sql,'maxRows':100000})['id'];deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    body=api.get('/api/batches/'+batch)
                    if body['status']!='started':break
                    time.sleep(.05)
                else:raise NativeError('SQLPad batch timeout')
                st=body['statements'][0]
                if st.get('error'):raise NativeError(st['error'])
                if st.get('incomplete'):raise NativeError('SQLPad result is incomplete')
                rows=api.get('/api/statements/'+st['id']+'/results')
                rows=[list(row.values()) if isinstance(row,dict) else row for row in rows]
            elif tool=='zeppelin':
                pid=api.call('/api/notebook/'+ds+'/paragraph',{'title':case['id'],'text':'%jdbc\n'+sql})['body']
                api.call('/api/notebook/run/'+ds+'/'+pid,{})
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    paragraph=api.get('/api/notebook/'+ds+'/paragraph/'+pid)['body']
                    if paragraph['status'] not in ('PENDING','RUNNING','READY'):break
                    time.sleep(.05)
                else:raise NativeError('Zeppelin paragraph timeout')
                if paragraph['status']!='FINISHED' or paragraph.get('results',{}).get('code')!='SUCCESS':raise NativeError(str(paragraph.get('results')))
                table=next(m['data'] for m in paragraph['results']['msg'] if m['type']=='TABLE')
                rows=[[None if v=='null' else v for v in row.split('\t')] for row in table.splitlines()[1:] if row]
            result=c.record(case,rows)
            if tool=='dataease' and len(rows)<len(case['expected']):
                prefix=case|{'expected':case['expected'][:len(rows)]}
                if not c.compare(rows,prefix):
                    result['status']='known_failure' if len(rows)==100 else 'incomplete'
                    result['failure_kind']='preview_limit';result['expected_full_rows']=len(case['expected'])
            if tool=='zeppelin' and result['status']=='mismatch' and known_client_value(tool,case,rows,state):
                result.update(status='known_failure',failure_kind='notebook_table_format',independent_source_control='passed')
        except Exception as exc:
            message=str(exc);known=(tool=='superset' and "'tuple' object does not support item assignment" in message) or (tool=='grafana' and 'invalid connection' in message)
            result={'id':case['id'],'status':'known_failure' if known else 'error','error':protect_error(exc,config)}
        yield result|{'version':version,'elapsed_seconds':round(time.monotonic()-started,6),'path':'native-api'}
    if tool=='sqlpad':
        case=next(r for r in cases if r['id']=='BASE-C03') if any(r['id']=='BASE-C03' for r in cases) else cases[0]
        saved=api.call('/api/queries',{'name':'mo-test saved metric '+state['run_id'],'connectionId':ds,'queryText':c.remap(case['sql'],state)})
        read=api.get('/api/queries/'+saved['id'])
        yield {'id':'SAVED-QUERY','status':'passed' if read['queryText']==c.remap(case['sql'],state) else 'mismatch','version':version,'path':'saved-query'}
    if tool=='superset':
        # Exercise native semantic registration separately from SQL Lab. A
        # connection or saved config is not evidence that charts rendered data.
        for domain in ['commerce','saas','marketing','finance','inventory','telemetry','support','workforce','supply','experiments']:
            try:
                api.call('/api/v1/dataset/',{'database':ds,'schema':state['schemas']['semantic'],'table_name':domain+'_fact'})
                yield {'id':'VIEW-REGISTRATION-'+domain,'status':'passed','path':'native-view-reflection','version':version}
            except Exception as e:
                yield {'id':'VIEW-REGISTRATION-'+domain,'status':'known_failure' if 'NullType() takes no arguments' in str(e) else 'error',
                       'error':protect_error(e,config),'issue':'https://github.com/matrixorigin/matrixone/issues/30045','path':'native-view-reflection','version':version}
        table='commerce_physical_'+uuid.uuid4().hex[:12]
        with c.connection() as cx,cx.cursor() as q:
            q.execute('CREATE TABLE '+c.identifier(state['schemas']['semantic'])+'.'+c.identifier(table)+' AS SELECT * FROM '+c.identifier(state['schemas']['semantic'])+'.commerce_fact')
        dataset=api.call('/api/v1/dataset/',{'database':ds,'schema':state['schemas']['semantic'],'table_name':table})['id']
        metrics=[{'metric_name':'net_value','expression':'SUM(net_amount)','metric_type':'sum'},
                 {'metric_name':'events','expression':'COUNT(*)','metric_type':'count'},
                 {'metric_name':'unique_entities','expression':'COUNT(DISTINCT entity_id)','metric_type':'count_distinct'}]
        api.call('/api/v1/dataset/'+str(dataset),{'metrics':metrics},method='put')
        yield {'id':'SAVED-PHYSICAL-METRICS','status':'passed','path':'saved-native-metrics','version':version}
        reference={r['id']:r for r in c.corpus('rill-metrics')}
        for sid in (1,91,101,191):
            pi=(sid-1)//10+1
            for grouped in (False,True):
                names=['category','net_value','events'] if grouped else ['events','net_value','unique_entities']
                frozen=reference[f'RILL-commerce-P{pi:02d}-T02' if grouped else f'RILL-commerce-P{pi:02d}-T01']
                expected=frozen['expected'] if grouped else [[r[0],r[2],r[4]] for r in frozen['expected']]
                case={'id':f'CHART-S{sid:03d}-'+str(grouped),'expected':expected,'order_check':True,'policy':'exact'}
                request={'datasource':{'id':dataset,'type':'table'},'queries':[{'columns':['category'] if grouped else [],'metrics':names[1:] if grouped else names,
                         'row_limit':100000,'filters':[{'col':'scenario_id','op':'==','val':sid}],'orderby':[['category',True]] if grouped else []}],
                         'result_format':'json','result_type':'full'}
                try:
                    response=api.call('/api/v1/chart/data',request)['result'][0]
                    if response.get('error'):raise NativeError(str(response['error']))
                    yield c.record(case,[[row.get(n) for n in names] for row in response['data']],path='native-chart-metrics',version=version)
                except Exception as e:
                    yield {'id':case['id'],'status':'known_failure' if "'tuple' object does not support item assignment" in str(e) else 'error','error':protect_error(e,config),'path':'native-chart-metrics','version':version}

def sdk(tool,state,config,cases,out):
    private=c.ROOT/'runtime'/state['run_id']/(tool+'-'+uuid.uuid4().hex[:12]);private.mkdir(parents=True,mode=0o700,exist_ok=False)
    input_path=private/'input.json';output_path=private/'output.json'
    payload={'tool':tool,'version':VERSIONS[tool],'credentials':credentials(state,config),
      'cases':[r|{'sql':c.remap(r['sql'],state)} for r in cases],
      'module_root':config.get('module_root'),'ssl':config.get('ssl',False)}
    input_path.write_text(json.dumps(payload,ensure_ascii=False));input_path.chmod(0o600)
    mapping=config.get('path_map',{})
    def translate(path):
        for prefix,replacement in sorted(mapping.items(),key=lambda x:-len(x[0])):
            if str(path).startswith(prefix+'/') or str(path)==prefix:return replacement+str(path)[len(prefix):]
        return str(path)
    values={'input':translate(input_path),'output':translate(output_path),'driver':translate(c.ROOT/'drivers'/(tool+'_sdk.py' if tool=='redash' else tool+'_sdk.cjs'))}
    command=[part.format(**values) for part in config['command']]
    # Private SDK stdout/stderr may contain connection configuration. They are
    # not exposed as artifacts; only scrubbed structured case records are used.
    with (private/'sdk.log').open('w') as log:
        proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=config.get('timeout',1800),check=False)
    if not output_path.exists():raise NativeError('SDK produced no structured output; inspect private runtime log')
    body=json.loads(output_path.read_text(),parse_float=c.D)
    if body.get('version')!=VERSIONS[tool]:raise NativeError('Native SDK version mismatch')
    if proc.returncode!=0:raise NativeError('Native SDK exited unsuccessfully')
    if tool=='lightdash':
        for r in body['records']:
            message=r.get('error','');known=('Warehouse credentials type were not recognised' in message or 'Invalid adapter type' in message)
            yield {'id':r['id'],'status':'known_failure' if known else 'error','error':protect_error(NativeError(message),config),'version':body['version'],'path':'native-adapter-factory','matrixone_sql_executed':False}
        return
    index={r['id']:r for r in cases}
    if len(body['records'])!=len(cases) or {r['id'] for r in body['records']}!=set(index):raise NativeError('Incomplete or duplicate SDK case coverage')
    for r in body['records']:
        if r.get('error'):
            known=tool=='evidence' and "Can't add new command when connection is in closed state" in r['error']
            yield {'id':r['id'],'status':'known_failure' if known else 'error','error':protect_error(NativeError(r['error']),config),'version':body['version'],'path':'native-sdk'}
        else:
            case=index[r['id']];result=c.record(case,r['rows'],version=body['version'],path='native-sdk-production-serialization')
            if tool=='redash' and result['status']=='mismatch' and known_client_value(tool,case,r['rows'],state):
                result.update(status='known_failure',failure_kind='client_precision_loss',independent_source_control='passed')
            yield result

def run(tool,state,config,out,limit=0):
    records=[]
    try:
        if not config:raise NativeError('Missing native runtime configuration for '+tool)
        config=resolve_config(config)
        if tool=='metabase':items=metabase(state,config,limit)
        elif tool=='rill':
            import rill
            items=rill.run(state,config,limit)
        else:
            cases=list(c.corpus('sql-projection'));cases=cases[:limit] if limit else cases
            items=sdk(tool,state,config,cases,out) if tool in ('redash','evidence','lightdash') else http_queries(tool,state,config,cases)
        for result in items:
            result['id']=tool+'::'+result['id'];result['tool']=tool;records.append(result)
            if len(records)%500==0:print(json.dumps({'tool':tool,'completed':len(records)}),flush=True)
    except Exception as exc:records.append({'id':tool+'::NATIVE-PREFLIGHT','tool':tool,'status':'error','error':protect_error(exc,config)})
    c.write_json(out/(tool+'-cases.json'),records);return records
