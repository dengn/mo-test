#!/usr/bin/env python3
"""Run isolated framework groups and enforce complete, non-skipped JUnit evidence."""
import argparse,hashlib,json,os,re,signal,subprocess,sys,time,uuid
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def inventory():return json.loads((ROOT/'projects.json').read_text())

def evaluate_junit(path,expected):
    result={'passed':[],'problems':[],'missing':list(expected)}
    if not Path(path).exists():return result
    try:cases=ET.parse(path).getroot().iter('testcase')
    except ET.ParseError as e:result['problems'].append({'name':'junit','status':'invalid','detail':str(e)});return result
    for case in cases:
        issue=next((child for child in case if child.tag in ['failure','error','skipped']),None)
        if issue is not None:
            if issue.tag=='skipped' and case.get('name') not in expected:continue
            result['problems'].append({'name':case.get('name'),'status':issue.tag})
        else:result['passed'].append(case.get('name'))
    result['missing']=sorted(set(expected)-set(result['passed']))
    return result

def process(command,env,log_path,timeout):
    with Path(log_path).open('w',encoding='utf-8') as log:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:return child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
            return 124

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group',default='all');parser.add_argument('--project',action='append',default=[])
    parser.add_argument('--list-groups-json',action='store_true')
    parser.add_argument('--python',help='Use an already provisioned interpreter for the selected group')
    parser.add_argument('--python-map',help='JSON mapping of group to already provisioned interpreter')
    parser.add_argument('--node',default='node');parser.add_argument('--output',type=Path)
    parser.add_argument('--timeout',type=int,default=300);parser.add_argument('--wait',type=int,default=90)
    args=parser.parse_args();catalog=inventory();groups=catalog['groups'];projects=catalog['projects']
    selected_projects=[p for p in projects if not args.project or p['id'] in args.project]
    unknown=set(args.project)-{p['id'] for p in projects}
    if unknown:parser.error('Unknown projects: '+','.join(sorted(unknown)))
    selected_groups=list(groups) if args.group=='all' else [args.group]
    if any(g not in groups for g in selected_groups):parser.error('Unknown regression group')
    selected_groups=[g for g in selected_groups if any(p['group']==g for p in selected_projects)]
    if not selected_groups:parser.error('Selected project does not belong to selected group')
    if args.list_groups_json:print(json.dumps(selected_groups));return 0
    if args.timeout<1 or args.wait<1:parser.error('Timeouts must be positive')
    interpreters=json.loads(Path(args.python_map).read_text()) if args.python_map else {}
    run_id=uuid.uuid4().hex[:12];output=(args.output or ROOT/'results'/run_id).resolve()
    output.mkdir(parents=True,exist_ok=False)
    report={'run_id':run_id,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'groups':[]}
    for group in selected_groups:
        started=time.monotonic();options=groups[group];directory=output/group;directory.mkdir();(directory/'runtime').mkdir()
        registry=directory/'databases.json';junit=directory/'junit.xml'
        python=args.python or interpreters.get(group) or str(ROOT/'.venvs'/group/'bin/python')
        selected=[p for p in selected_projects if p['group']==group]
        expected=[name for p in selected for name in p['gate_tests']]
        env=dict(os.environ,MO_RUN_ID=run_id,MO_REGISTRY=str(registry),MO_RUNTIME_DIR=str(directory/'runtime'),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONPATH=str(ROOT))
        entry={'group':group,'projects':[p['id'] for p in selected],'expected_tests':expected,'requirements_sha256':hashlib.sha256((ROOT/options['requirements']).read_bytes()).hexdigest()}
        try:
            if not Path(python).exists():raise FileNotFoundError('Install this group with setup.py first, or provide --python/--python-map')
            readiness=process([python,str(ROOT/'shared.py'),'--wait',str(args.wait),'--environment',str(directory/'environment.json'),'--packages',json.dumps(options['packages'])],env,directory/'readiness.log',args.wait+30)
            entry['readiness_exit_code']=readiness
            if readiness==0:
                if group=='javascript':
                    # Node's own test runner sets a failing exit status on assertion/hook failure.
                    command=[args.node,'--test','--test-force-exit','--test-reporter=junit','--test-reporter-destination='+str(junit)]
                    if args.project:command+=['--test-name-pattern=^(?:'+'|'.join(re.escape(name) for name in expected)+')$']
                    command+=[options['module']]
                else:
                    command=[python,'-m','pytest',options['module'],'--junitxml='+str(junit),'--basetemp='+str(directory/'runtime/pytest'),'-q']
                    if args.project:command+=['--project',','.join(p['id'] for p in selected)]
                entry['test_exit_code']=process(command,env,directory/'tests.log',args.timeout)
            else:entry['test_exit_code']=None
            entry.update(evaluate_junit(junit,expected))
        except Exception as e:entry.update(test_exit_code=None,passed=[],missing=expected,problems=[{'name':'runner','status':'error','detail':str(e)}])
        finally:
            try:entry['cleanup_exit_code']=process([python,str(ROOT/'shared.py'),'--cleanup',str(registry),'--run-id',run_id],env,directory/'cleanup.log',60)
            except Exception as e:entry.update(cleanup_exit_code=None,cleanup_error=str(e))
        entry['status']='PASS' if entry.get('readiness_exit_code')==0 and entry['test_exit_code']==0 and entry['cleanup_exit_code']==0 and not entry['missing'] and not entry['problems'] else 'FAIL'
        entry['elapsed_seconds']=round(time.monotonic()-started,3);report['groups'].append(entry)
        (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(group,entry['status'],f"{len(entry['passed'])}/{len(expected)} expected tests passed",flush=True)
    report.update(status='PASS' if all(g['status']=='PASS' for g in report['groups']) else 'FAIL',tested_projects=sum(len(g['projects']) for g in report['groups']),passed_tests=sum(len(g['passed']) for g in report['groups']))
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
