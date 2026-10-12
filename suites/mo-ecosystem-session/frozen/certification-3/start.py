from runtime import *
base=(OLD/'connect.properties').read_text()
for eos in [False,True]:
 prefix='cert3-eos' if eos else 'cert3';port=18085 if eos else 18084
 s=base.replace('mo-runtime-connect',prefix+'-connect').replace('mo-connect-',prefix+'-').replace('18083',str(port)).replace('offset.flush.interval.ms=1000','offset.flush.interval.ms='+('60000' if eos else '1000'))
 s+='\nscheduled.rebalance.max.delay.ms=1000\n'
 (B/('eos-connect.properties' if eos else 'connect.properties')).write_text(s)
start('mo');start('kafka');start('nifi')
poll(lambda:sql(6001,None,'SELECT 1'),150)
poll(lambda:__import__('socket').create_connection(('127.0.0.1',19092),timeout=1),60)
start('connect');poll(lambda:api('GET','/connector-plugins'),100)
poll(lambda:requests.get('http://127.0.0.1:10088/nifi-api/flow/process-groups/root',timeout=5).status_code==200,100)
print('READY',flush=True)
