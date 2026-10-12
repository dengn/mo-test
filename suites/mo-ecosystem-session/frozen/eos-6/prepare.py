from runtime import *
from kafka import KafkaConsumer
start('mo');start('kafka')
poll(lambda:sql('SELECT 1',database='mo_catalog'),100)
def kafka_ready():
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));c.topics();c.close();return True
poll(kafka_ready,60)
for port in [6001,13306]:
 poll(lambda:sql('SELECT 1',port=port,database='mysql' if port==13306 else 'mo_catalog'),30)
 sql('CREATE DATABASE eos6',port=port,database='mysql' if port==13306 else 'mo_catalog')
 sql('CREATE TABLE ledger(scope VARCHAR(64),event_id BIGINT,digest VARCHAR(64),delta BIGINT,first_partition INT,first_offset BIGINT,PRIMARY KEY(scope,event_id))',port=port)
 sql('CREATE TABLE totals(scope VARCHAR(64) PRIMARY KEY,n BIGINT)',port=port)
 sql('CREATE TABLE checkpoints(scope VARCHAR(64),partition_id INT,last_offset BIGINT,epoch BIGINT,PRIMARY KEY(scope,partition_id))',port=port)
 sql('CREATE TABLE raw_effects(scope VARCHAR(64),event_id BIGINT,delta BIGINT)',port=port)
 sql('CREATE TABLE quarantine(scope VARCHAR(64),partition_id INT,record_offset BIGINT,event_id BIGINT,reason VARCHAR(128),PRIMARY KEY(scope,partition_id,record_offset))',port=port)
cmd=[sys.executable,str(B/'commit_ack_proxy.py')];p=subprocess.Popen(cmd,stdout=(B/'proxy.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'proxy.pid').write_text(str(p.pid))
dump(B/'environment.json',{'runtime_ref':REF,'CPU_quota':Path('/sys/fs/cgroup/cpu.max').read_text(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text(),'MO_version':sql('SELECT VERSION()'),'MySQL_version':sql('SELECT VERSION()',port=13306),'kafka_python':__import__('kafka').__version__,'scope':'shared retained state; new eos6 fixtures; Kafka + MO + MySQL; no Connect/NiFi/PG worker started; prior 256MB disk cache profile retained','binary_sha256':hashlib.sha256(Path('/workspace/matrixone/mo-service').read_bytes()).hexdigest()})
print('EOS6 READY',flush=True)
