from common import *
import pymysql
resume=os.environ.get('RT2_MYSQL_RESUME')=='1'
out=json.loads((B/'mysql-jdbc-outage-control.json').read_text()) if resume else {'scope':'independent MySQL8.4.11 daemon inside existing local test container; source daemon remains running; same Debezium JDBC sink version and topic, pre-created target schema','cases':[]}
def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
container='mo-types-mysql';data='/tmp/mo-rt2-control';socket='/tmp/mo-rt2-control.sock';pidfile='/tmp/mo-rt2-control.pid'
if not resume:
 docker('exec',container,'sh','-c','mkdir -p '+data+' && chown mysql:mysql '+data)
 docker('exec','-u','mysql',container,'mysqld','--initialize-insecure','--datadir='+data,'--log-error=/tmp/mo-rt2-control-init.log')
args=['mysqld','--datadir='+data,'--socket='+socket,'--pid-file='+pidfile,'--port=3307','--bind-address=0.0.0.0','--skip-log-bin','--mysqlx=0','--innodb-buffer-pool-size=64M','--max-connections=30','--log-error=/tmp/mo-rt2-control.log']
def server_start():docker('exec','-d','-u','mysql',container,*args)
if not resume:
 server_start()
 poll(lambda:subprocess.run(['docker','exec',container,'mysqladmin','--socket='+socket,'-uroot','ping'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0,60)
 docker('exec',container,'mysql','--socket='+socket,'-uroot','-e',"CREATE USER 'rt2_control'@'%' IDENTIFIED BY 'control-local'; GRANT ALL ON rt2_kafka.* TO 'rt2_control'@'%'; CREATE DATABASE rt2_kafka;")
ip=json.loads(docker('inspect',container))[0]['NetworkSettings']['Networks']['bridge']['IPAddress'];out['control_endpoint']={'ip':ip,'port':3307}
def query(stmt):
 with pymysql.connect(host=ip,port=3307,user='rt2_control',password='control-local',database='rt2_kafka',autocommit=True,charset='utf8mb4',connect_timeout=3,read_timeout=10) as d,d.cursor() as c:
  c.execute(stmt);return c.fetchall() if c.description else c.rowcount
if not resume:query('CREATE TABLE wide(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(300),ts DATETIME(6),doc JSON,updated BIGINT)')
cfg=json.loads((B/'wide-sink-config.json').read_text());cfg.update({'connection.url':f'jdbc:mysql://{ip}:3307/rt2_kafka?useSSL=false','connection.username':'rt2_control','connection.password':'control-local'})
if not resume:api('PUT','/connectors/rt2-mysql-control/config',cfg);dump(B/'mysql-control-sink-config.json',cfg)
def rows(control=False):
 stmt='SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated FROM wide ORDER BY id'
 rr=query(stmt) if control else sql(13306,'rt2_kafka',stmt)
 return [tuple(x[:7])+(json.loads(x[7]) if x[7] is not None else None,)+tuple(x[8:]) for x in rr]
def wait(name,timeout=80):
 start_t=time.monotonic();expected=rows();actual=None
 while time.monotonic()-start_t<timeout:
  try:actual=rows(True)
  except Exception as e:actual=str(e)
  if expected==actual:break
  time.sleep(1)
 case={'name':name,'status':'passed' if actual==expected else 'failed','source':expected,'sink':actual,'elapsed_s':round(time.monotonic()-start_t,2),'connector_status':api('GET','/connectors/rt2-mysql-control/status')};out['cases'].append(case);dump(B/'mysql-jdbc-outage-control.json',out);print(name,case['status'],flush=True);return case['status']=='passed'
assert wait('MySQL-control-initial-topic-replay')
pid=int(docker('exec',container,'cat',pidfile));cmd=docker('exec',container,'cat','/proc/'+str(pid)+'/cmdline');assert data in cmd
docker('exec',container,'sh','-c','kill -9 '+str(pid));out['fault']={'signal':'SIGKILL','owned_mysql_container_pid':pid,'datadir':data}
sql(13306,'rt2_kafka',"UPDATE wide SET name='MySQL control SIGKILL😀',ts='2026-10-11 20:00:00.000001',updated=600 WHERE id=3")
sql(13306,'rt2_kafka',"INSERT INTO wide(id,u,name,updated) VALUES(104,18446744073709551615,'独立对照停机事件',601)")
time.sleep(6);out['while_target_down']=api('GET','/connectors/rt2-mysql-control/status');dump(B/'mysql-jdbc-outage-control.json',out);server_start();poll(lambda:query('SELECT 1'),80)
if not wait('MySQL-control-SIGKILL-auto-recovery',65):
 api('POST','/connectors/rt2-mysql-control/restart?includeTasks=true&onlyFailed=true');wait('MySQL-control-after-explicit-task-restart')
print('MYSQL JDBC CONTROL DONE',flush=True)
