from runtime import *
import importlib.metadata as metadata
start('mo');poll(lambda:sql('SELECT 1',database='mo_catalog'),100)
for port in [6001,13306]:
 poll(lambda:sql('SELECT 1',port=port,database='mysql' if port==13306 else 'mo_catalog'),30)
 sql('CREATE DATABASE etl10000',port=port,database='mysql' if port==13306 else 'mo_catalog')
dump(B/'environment.json',{'runtime_ref':REF,'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text(),'initial_resources':resources(),'versions':{p:metadata.version(p) for p in ['petl','polars','duckdb','dask','pyarrow','pandas','sqlalchemy','pymysql']},'MO':sql('SELECT VERSION(),@@sql_mode'),'MySQL':sql('SELECT VERSION(),@@sql_mode',port=13306),'scope':'retained data and 256MB disk cache settings; isolated etl10000 fixtures; no broker/Connect/NiFi/PG started; 5 routes x20 profiles x5 scenarios x10 seeds x2 endpoints','binary_sha256':hashlib.sha256(Path('/workspace/matrixone/mo-service').read_bytes()).hexdigest()})
print('ETL10000 READY',flush=True)
