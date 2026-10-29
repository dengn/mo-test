import os,json,pathlib,subprocess,sys
B=pathlib.Path(__file__).resolve().parent;env=dict(os.environ,**json.loads((B/'airflow-env.json').read_text()));env['PATH']=str(B/'venv/bin')+':'+env['PATH']
r=subprocess.run([str(B/'venv/bin/airflow')]+sys.argv[1:],env=env);raise SystemExit(r.returncode)
