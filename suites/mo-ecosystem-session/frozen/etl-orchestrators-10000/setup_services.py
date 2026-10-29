import os,json,subprocess,pathlib,requests,hashlib
B=pathlib.Path('/workspace/work/etl-orchestrators-10000');D=B/'apache-dolphinscheduler-3.4.2-bin'
p=D/'standalone-server/conf/common.properties';s=p.read_text().replace('sudo.enable=true','sudo.enable=false');p.write_text(s)
p=D/'standalone-server/conf/application.yaml';s=p.read_text().replace('enabled: true\n    # Master max','enabled: false\n    # Master max').replace('enabled: true\n    # Worker max','enabled: false\n    # Worker max');s=s.replace('task-executor-thread-size: 100','task-executor-thread-size: 4');p.write_text(s)
receipts=[]
for kind,artifact in [('task-plugins','dolphinscheduler-task-shell'),('storage-plugins','dolphinscheduler-storage-hdfs')]:
 dest=D/'plugins'/kind/(artifact+'-3.4.2-shade.jar');dest.parent.mkdir(parents=True,exist_ok=True)
 url=f'https://repo.maven.apache.org/maven2/org/apache/dolphinscheduler/{artifact}/3.4.2/{artifact}-3.4.2-shade.jar'
 if not dest.exists():
  r=requests.get(url,timeout=60);r.raise_for_status();dest.write_bytes(r.content)
 receipts.append({'artifact':artifact,'url':url,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
(B/'dolphin-plugin-receipts.json').write_text(json.dumps(receipts,indent=2))
if not (B/'dolphin.pid').exists():
 env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64',JAVA_OPTS='-Xms128m -Xmx768m -XX:ActiveProcessorCount=4 -Djava.io.tmpdir=/tmp')
 p=subprocess.Popen(['bash',str(D/'standalone-server/bin/start.sh')],cwd=D,env=env,stdout=(B/'dolphin.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'dolphin.pid').write_text(str(p.pid));print('Dolphin PID',p.pid,flush=True)
if not (B/'airflow.pid').exists():
 env=dict(os.environ,AIRFLOW_HOME=str(B/'airflow-home'),AIRFLOW__CORE__LOAD_EXAMPLES='False',AIRFLOW__CORE__PARALLELISM='2',AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG='2',AIRFLOW__API__WORKERS='1',AIRFLOW__DAG_PROCESSOR__PARSING_PROCESSES='1',AIRFLOW__CORE__EXECUTOR='LocalExecutor',AIRFLOW__API__PORT='18081')
 (B/'airflow-env.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('AIRFLOW')},indent=2))
 p=subprocess.Popen([str(B/'venv/bin/airflow'),'standalone'],cwd=B,env=env,stdout=(B/'airflow.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'airflow.pid').write_text(str(p.pid));print('Airflow PID',p.pid,flush=True)
