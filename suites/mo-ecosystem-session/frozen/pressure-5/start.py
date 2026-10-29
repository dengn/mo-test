from runtime import *
start('mo');start('kafka');poll(lambda:sql('SELECT 1',database='mo_catalog'),90);poll(lambda:requests.get('http://127.0.0.1:7001/metrics',timeout=5).status_code==200,30)
start('connect');poll(lambda:api('GET','/connector-plugins'),90)
for port in [6001,13306]:sql('CREATE DATABASE stress5',port=port,database='mysql' if port==13306 else 'mo_catalog')
dump(B/'environment.json',{'runtime_ref':REF,'resources':resources(),'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text(),'versions':{'MO':sql('SELECT VERSION(),@@sql_mode,@@time_zone'),'MySQL':sql('SELECT VERSION(),@@sql_mode,@@time_zone',port=13306),'PG':psql('SHOW server_version')},'configuration_changes':'all MO shared disk caches cap256MB/eviction30s; prior data retained; new KafkaConnect group and port18087; PG initializer skips initdb on existing fixture; Go compilation cache reclaimed'})
print('STRESS5 READY',flush=True)
