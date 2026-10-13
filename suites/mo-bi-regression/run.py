"""mo-test analytical/BI regression: independent inputs, references and failures."""
import argparse,collections,json,os,re,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
import common as c
import fixtures
import run_sql

TOOLS=['metabase','superset','grafana','redash','dataease','evidence','rill','zeppelin','sqlpad','lightdash']
NATIVE_COUNTS={'metabase':6880,'superset':553,'grafana':535,'redash':534,'dataease':535,'evidence':534,'rill':800,'zeppelin':534,'sqlpad':535,'lightdash':4}

def outcome(records,mode):
    if not records:return 2
    allowed={'passed'}|({'known_failure'} if mode=='observe' else set())
    return 0 if all(r['status'] in allowed for r in records) else 1

def report(out,records,meta,mode):
    exit_code=outcome(records,mode);statuses=dict(collections.Counter(r['status'] for r in records))
    data={'schema_version':1,**meta,'mode':mode,'case_count':len(records),'statuses':statuses,
          'passed':exit_code==0 and not statuses.get('known_failure'),'exit_code':exit_code,'cases':records,
          'scope':'BI execution is native only for BI profiles. Known failures remain failures in strict mode; observe records them as JUnit skipped, never passed.'}
    c.write_json(out/'results.json',data)
    xml=ET.Element('testsuite',name='mo-bi-regression',tests=str(len(records)),failures=str(sum(r['status']!='passed' and not (mode=='observe' and r['status']=='known_failure') for r in records)),skipped=str(sum(mode=='observe' and r['status']=='known_failure' for r in records)))
    for r in records:
        node=ET.SubElement(xml,'testcase',name=r['id'],classname='matrixone.bi-regression',time=str(r.get('elapsed_seconds',0)))
        if r['status']=='known_failure' and mode=='observe':ET.SubElement(node,'skipped',message='Observed known compatibility failure')
        elif r['status']!='passed':ET.SubElement(node,'failure',message=r['status']).text=json.dumps(r,ensure_ascii=False)
    ET.ElementTree(xml).write(out/'junit.xml',encoding='utf8',xml_declaration=True)
    return exit_code

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',choices=['smoke','sql','metabase','bi','extreme','spill'],default='smoke')
    p.add_argument('--tool',choices=TOOLS,action='append')
    p.add_argument('--mode',choices=['strict','observe'],default='strict')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--expected-commit')
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--fixture-state',type=Path)
    p.add_argument('--native-config',type=Path)
    p.add_argument('--keep-data',action='store_true')
    p.add_argument('--list',action='store_true')
    p.add_argument('--include-boundaries',action='store_true')
    p.add_argument('--dedicated-instance',action='store_true')
    p.add_argument('--mo-pid',type=int)
    p.add_argument('--spill-root',type=Path)
    p.add_argument('--metrics-url')
    a=p.parse_args()
    if a.workers<1 or a.workers>32 or a.limit<0:p.error('workers must be 1..32; limit must be nonnegative')
    if a.tool and a.profile not in ('bi','metabase'):p.error('--tool requires a native BI profile')
    if a.profile=='metabase' and a.tool and a.tool!=['metabase']:p.error('metabase profile selects only Metabase')
    if a.profile=='extreme' and not a.list and (not a.dedicated_instance or not a.mo_pid):p.error('extreme requires --dedicated-instance and --mo-pid for resource monitoring')
    if a.profile=='spill' and not a.list and (not a.dedicated_instance or not a.mo_pid or not a.spill_root or not a.metrics_url):p.error('spill requires --dedicated-instance, --mo-pid, --spill-root and --metrics-url')
    if a.include_boundaries and (a.profile!='extreme' or (not a.list and (not a.dedicated_instance or not a.mo_pid))):p.error('boundary SQL requires extreme, --dedicated-instance and --mo-pid')
    if a.profile in ('bi','metabase'):
        tools=['metabase'] if a.profile=='metabase' else a.tool or TOOLS
        if not a.native_config and not a.list:p.error('native BI execution requires --native-config')
        planned={tool:NATIVE_COUNTS[tool] for tool in tools}
        cases=[]
    elif a.profile=='spill':planned={'spill':14};cases=[]
    else:
        cases=run_sql.selected(a.profile);planned={a.profile:len(cases)}
        if a.profile=='extreme' and not a.include_boundaries:
            # Retain every imported boundary and historical status in the corpus.
            # The default expensive profile replays historically bounded passes.
            cases=[r for r in cases if r['historical_status']=='pass'];planned['boundaries_not_selected']=11
        if a.limit:cases=cases[:a.limit]
    if a.list:
        print(json.dumps({'profile':a.profile,'planned':planned,'selected_sql':len(cases),'limit':a.limit,'native_tools':tools if a.profile in ('bi','metabase') else []},indent=2));return 0
    if a.out.exists():p.error('Output already exists; choose a new run directory')
    a.out.mkdir(parents=True,mode=0o700);state=None;created_here=False;records=[]
    meta={'profile':a.profile,'planned':planned,'requested_limit':a.limit,'source_manifest':c.digest(c.MANIFEST),'started_utc':c.datetime.datetime.now(c.datetime.timezone.utc).isoformat()}
    started=time.monotonic()
    try:
        from verify import verify
        meta['corpus_integrity']=verify()
        meta['target']=target=c.preflight(a.expected_commit)
        state=fixtures.reuse(a.fixture_state,target) if a.fixture_state else fixtures.create(a.out,target)
        created_here=not bool(a.fixture_state);meta['schemas']=state['schemas']
        if a.profile in ('bi','metabase'):
            import native
            config=native.load_config(a.native_config)
            for tool in tools:
                records+=native.run(tool,state,config.get(tool),a.out,limit=a.limit)
        elif a.profile=='spill':
            import spill
            records=spill.run(state,a)
        elif a.profile=='extreme':
            import stress
            records=stress.run(cases,state,a)
        else:records=run_sql.execute(cases,state,a.mode,a.out,a.workers)
    except Exception as exc:
        records.append({'id':'HARNESS-PREFLIGHT','status':'error','error':c.safe_error(exc)})
        if state is None and (a.out/'fixture-state.json').exists():state=json.loads((a.out/'fixture-state.json').read_text());created_here=True
    finally:
        if state and created_here and not a.keep_data:
            try:fixtures.cleanup(state);meta['owned_schema_cleanup']='completed'
            except Exception as exc:records.append({'id':'HARNESS-CLEANUP','status':'error','error':c.safe_error(exc)})
        elif state:meta['owned_schema_cleanup']='preserved'
    meta['elapsed_seconds']=round(time.monotonic()-started,3)
    code=report(a.out,records,meta,a.mode)
    print(json.dumps({'out':str(a.out),'exit_code':code,'statuses':dict(collections.Counter(r['status'] for r in records))}));return code

if __name__=='__main__':sys.exit(main())
