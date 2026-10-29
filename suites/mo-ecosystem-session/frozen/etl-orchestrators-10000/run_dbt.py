import pathlib,subprocess,os,json,datetime
B=pathlib.Path(__file__).resolve().parent;P=B/'dbt-project';results=[]
for target in ['mo','mysql']:
 out=B/f'dbt-artifacts-{target}';log=B/f'dbt-logs-{target}'
 cmd=[str(B/'dbt-venv/bin/dbt'),'build','--project-dir',str(P),'--profiles-dir',str(P),'--target',target,'--target-path',str(out),'--log-path',str(log)]
 with (B/f'dbt-build-{target}.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 receipt={'target':target,'command':cmd,'exit_code':r.returncode,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()};results.append(receipt);(B/'dbt-build-receipts.json').write_text(json.dumps(results,indent=2));print(receipt,flush=True)
