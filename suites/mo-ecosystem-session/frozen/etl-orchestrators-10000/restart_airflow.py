import pathlib,json,os,signal,subprocess
B=pathlib.Path(__file__).resolve().parent;pid=int((B/'airflow.pid').read_text());assert b'airflow\x00standalone' in pathlib.Path('/proc',str(pid),'cmdline').read_bytes();os.killpg(pid,signal.SIGTERM)
env=dict(os.environ,**json.loads((B/'airflow-env.json').read_text()));env['PATH']=str(B/'venv/bin')+':'+env['PATH']
p=subprocess.Popen([str(B/'venv/bin/airflow'),'standalone'],cwd=B,env=env,stdout=(B/'airflow-restart.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'airflow.pid').write_text(str(p.pid));print(p.pid)
