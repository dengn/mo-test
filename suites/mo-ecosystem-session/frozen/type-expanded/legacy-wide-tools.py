import json,subprocess,traceback,datetime
from pathlib import Path
from decimal import Decimal
import pymysql
B=Path(__file__).parent;old=Path('/workspace/work/etl-expanded');out={'cases':[]}
def conn(port=6001):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='tool_types',autocommit=True)
ddl='id BIGINT PRIMARY KEY,large_signed BIGINT,large_unsigned BIGINT UNSIGNED,d38 DECIMAL(38,18),d65 DECIMAL(65,30),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON'
wide=Decimal('9'*35+'.'+'9'*30);precise=Decimal('12345678901234567890.123456789012345678')
want=[(1,9007199254740993,18446744073709551615,precise,wide,b'\x00\xff\x80abc','中文 😀',datetime.datetime(2026,10,11,12,0,0,123456),'{"n":9007199254740993}'),(2,-9223372036854775808,0,Decimal('-12345678901234567890.123456789012345678'),Decimal('-'+'9'*35+'.'+'9'*30),b'','',None,'[]'),(3,None,None,None,None,None,None,None,None)]
for port in [6001,13306]:
 with conn(port) as d,d.cursor() as c:c.execute('DROP TABLE IF EXISTS wide_tools');c.execute('CREATE TABLE wide_tools('+ddl+')');c.executemany('INSERT INTO wide_tools VALUES('+','.join(['%s']*9)+')',want)
def normalized(rows):return [tuple(r[:-1])+(json.loads(r[-1]) if r[-1] is not None else None,) for r in rows]
def read(table):
 with conn() as d,d.cursor() as c:c.execute('SELECT * FROM '+table+' ORDER BY id');return c.fetchall()
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:300],flush=True);(B/'legacy-wide-tools-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
def datax(port,adapted):
 target='datax_wide_'+str(port)+'_'+str(adapted).lower();stage=target+'_stage'
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS '+stage);c.execute('CREATE TABLE '+stage+'(id BIGINT PRIMARY KEY,large_signed VARCHAR(100),large_unsigned VARCHAR(100),d38 VARCHAR(100),d65 VARCHAR(100),payload VARBINARY(100),name VARCHAR(100),ts VARCHAR(100),doc VARCHAR(500))');c.execute('DROP TABLE IF EXISTS '+target);c.execute('CREATE TABLE '+target+'('+ddl+')')
 cols=['id','large_signed','large_unsigned','d38','d65','payload','name','ts','doc'];q='SELECT id,'+','.join('CAST('+x+' AS CHAR) AS '+x if x in ['ts','doc'] or adapted and x in ['large_signed','large_unsigned','d38','d65'] else x for x in cols[1:])+' FROM wide_tools ORDER BY id'
 job=json.loads((old/'datax-staged-jdbc.json').read_text());content=job['job']['content'][0];rp=content['reader']['parameter'];rp['password']='111' if port==6001 else 'types-local';rp['connection']=[{'jdbcUrl':[f'jdbc:mysql://127.0.0.1:{port}/tool_types?useSSL=false&allowPublicKeyRetrieval=true&useUnicode=true&characterEncoding=utf8'],'querySql':[q]}];wp=content['writer']['parameter'];wp['column']=cols;wp['connection']=[{'jdbcUrl':'jdbc:mysql://127.0.0.1:6001/tool_types?useSSL=false&useUnicode=true&characterEncoding=utf8','table':[stage]}]
 p=B/(target+'.json');p.write_text(json.dumps(job));args=['java','-server','-Xms128m','-Xmx512m','-Dfile.encoding=UTF-8','-Ddatax.home='+str(old/'datax'),'-Dlogback.configurationFile='+str(old/'datax/conf/logback.xml'),'-classpath',str(old/'datax/lib/*'),'com.alibaba.datax.core.Engine','-mode','standalone','-jobid','-1','-job',str(p)]
 with (B/(target+'.log')).open('w') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=90)
 if r.returncode:raise AssertionError({'job_exit':r.returncode,'log_tail':(B/(target+'.log')).read_text()[-3000:]})
 with conn() as d,d.cursor() as c:c.execute(f'INSERT INTO {target} SELECT id,CAST(large_signed AS SIGNED),CAST(large_unsigned AS UNSIGNED),CAST(d38 AS DECIMAL(38,18)),CAST(d65 AS DECIMAL(65,30)),payload,name,CAST(ts AS DATETIME(6)),CAST(doc AS JSON) FROM {stage}')
 got=read(target);assert normalized(got)==normalized(want),(got,want)
 return {'rows':got,'all_values_exact':True,'numeric_text_adapter':adapted,'temporal_staging':True,'source_port':port,'driver':'bundled Connector/J 5.1.47'}
for port in [6001,13306]:
 case('DataX_'+str(port)+'_numeric_native_source_and_temporal_stage',lambda port=port:datax(port,False))
 case('DataX_'+str(port)+'_numeric_text_adapter_and_temporal_stage',lambda port=port:datax(port,True))
from pyspark.sql import SparkSession
s=SparkSession.builder.master('local[2]').appName('mo-wide-types').config('spark.ui.enabled','false').config('spark.driver.memory','512m').config('spark.sql.session.timeZone','UTC').config('spark.jars','/workspace/work/path-verification/jars/mysql-jdbc.jar').getOrCreate();s.sparkContext.setLogLevel('ERROR')
props={'user':'root','password':'111','driver':'com.mysql.cj.jdbc.Driver','batchsize':'2','isolationLevel':'READ_COMMITTED'}
def spark_direct(port):
 pr=dict(props,password='111' if port==6001 else 'types-local');df=s.read.jdbc(f'jdbc:mysql://127.0.0.1:{port}/tool_types?useSSL=false','wide_tools',properties=pr);rs=[tuple(r) for r in df.orderBy('id').collect()];assert normalized(rs)==normalized(want);return {'schema':df.schema.simpleString(),'rows':rs}
for port in [6001,13306]:case('Spark_'+str(port)+'_Decimal65_native_schema_limit',lambda port=port:spark_direct(port))
def spark_text(port):
 pr=dict(props,password='111' if port==6001 else 'types-local');q='(SELECT id,large_signed,large_unsigned,d38,CAST(d65 AS CHAR) AS d65,payload,name,ts,doc FROM wide_tools) t';df=s.read.jdbc(f'jdbc:mysql://127.0.0.1:{port}/tool_types?useSSL=false',q,properties=pr);rs=[tuple(r) for r in df.orderBy('id').collect()]
 converted=[tuple(r[:2])+(int(r[2]) if r[2] is not None else None,r[3],Decimal(r[4]) if r[4] is not None else None)+tuple(r[5:]) for r in rs];assert normalized(converted)==normalized(want),(converted,want)
 target='spark_wide_'+str(port)
 with conn() as d,d.cursor() as c:c.execute('DROP TABLE IF EXISTS '+target);c.execute('CREATE TABLE '+target+'('+ddl+')')
 df.repartition(2).write.jdbc('jdbc:mysql://127.0.0.1:6001/tool_types?useSSL=false',target,mode='append',properties=props);got=read(target);assert normalized(got)==normalized(want),(got,want)
 return {'read_schema':df.schema.simpleString(),'sink_rows':got,'all_fields_exact':True,'adapter':'CAST only Decimal65 to CHAR in source SQL; preserve unsigned64 as Spark Decimal20,0'}
for port in [6001,13306]:case('Spark_'+str(port)+'_wide_unsigned_decimal_binary_JSON_read_and_write_adapter',lambda port=port:spark_text(port))
s.stop()
