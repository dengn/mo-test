from runtime import *
D=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
r=subprocess.run(D+['start','mo-minio-local','mo-types-mysql'],capture_output=True,text=True);dump(B/'docker-start.json',{'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});assert r.returncode==0
start('mo');poll(lambda:sql('SELECT 1',database='mo_catalog'),100)
for port in [6001,13306]:poll(lambda:sql('SELECT 1',port=port,database='mo_catalog' if port==6001 else 'mysql'),60);sql('CREATE DATABASE IF NOT EXISTS '+DS,port=port,database=None)
dump(B/'environment.json',{'runtime_ref':REF,'binary_sha256':hashlib.sha256(Path('/workspace/matrixone/mo-service').read_bytes()).hexdigest(),'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text(),'initial_resources':resources(),'scope':'User requests5000newcases per involved tool, heavier mixed/failure/schema/concurrentloads; shared4CPU/16GiB notindependentcapacity; preservedolddata; freshheavy5000db; all nativevsadaptedprofile outcomesseparate'})
print('READY',flush=True)
