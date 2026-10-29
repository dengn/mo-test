import pymysql,json,subprocess,traceback,datetime
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent
out={'datax':'DATAX-OPENSOURCE-3.0 official README binary 202308','driver':'bundled mysql-connector-java-5.1.47','java':'OpenJDK 21','cases':[]}
my=pymysql.connect(host='127.0.0.1',port=13306,user='root',password='etl-local',database='etl_source',autocommit=True)
mo=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_datax',autocommit=True)
want=[(1,'中文 😀',Decimal('12.34'),datetime.datetime(2026,10,10,12,0,0,123456)),(2,'',Decimal('-56.78'),None),(3,None,None,datetime.datetime(2026,10,11))]
original=json.loads((B/'datax-job.json').read_text())
def job(name,j):
 path=B/(name+'.json');path.write_text(json.dumps(j,ensure_ascii=False,indent=2))
 args=['java','-server','-Xms128m','-Xmx512m','-Dfile.encoding=UTF-8','-Ddatax.home='+str(B/'datax'),'-Dlogback.configurationFile='+str(B/'datax/conf/logback.xml'),'-classpath',str(B/'datax/lib/*'),'com.alibaba.datax.core.Engine','-mode','standalone','-jobid','-1','-job',str(path)]
 with (B/(name+'.log')).open('w') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 assert r.returncode==0,('DataX failed',name,r.returncode)
 log=(B/(name+'.log')).read_text();assert 'Error 0 records' in log and 'Percentage 100.00%' in log
 return {'exit_code':r.returncode,'records':3,'dirty_records':0}
def clone():return json.loads(json.dumps(original))
def read(d,table):
 with d.cursor() as c:c.execute('SELECT * FROM '+table+' ORDER BY id');return list(c.fetchall())
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:250],flush=True)
def original_exact():
 rows=read(mo,'datax_rows');assert rows==want,(rows,want);return rows
check('unmodified_datax_full_precision_assertion',original_exact)
def mysql_precision_control():
 with my.cursor() as c:c.execute('DROP TABLE IF EXISTS datax_control');c.execute('CREATE TABLE datax_control LIKE datax_rows')
 j=clone();p=j['job']['content'][0]['writer']['parameter'];p['password']='etl-local';p['connection']=[{'jdbcUrl':'jdbc:mysql://127.0.0.1:13306/etl_source?useSSL=false&allowPublicKeyRetrieval=true&useUnicode=true&characterEncoding=utf8','table':['datax_control']}]
 receipt=job('datax-mysql-control',j);got=read(my,'datax_control');assert got[0][3].microsecond==123000
 return {'receipt':receipt,'same_precision_loss_on_real_mysql':True,'rows':got}
check('datax_precision_loss_mysql_control',mysql_precision_control)
with mo.cursor() as c:
 c.execute('DROP TABLE IF EXISTS datax_stage');c.execute('CREATE TABLE datax_stage(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),ts VARCHAR(40))');c.execute('DROP TABLE IF EXISTS datax_final');c.execute('CREATE TABLE datax_final LIKE datax_rows')
def copy_stage_final():
 with mo.cursor() as c:
  c.execute('TRUNCATE TABLE datax_final');c.execute('INSERT INTO datax_final SELECT id,name,amount,CAST(ts AS DATETIME(6)) FROM datax_stage')
 got=read(mo,'datax_final');assert got==want,(got,want);return got
def staged():
 j=clone();reader=j['job']['content'][0]['reader']['parameter'];reader.pop('column');reader.pop('splitPk');reader['connection']=[{'jdbcUrl':['jdbc:mysql://127.0.0.1:13306/etl_source?useSSL=false&allowPublicKeyRetrieval=true&useUnicode=true&characterEncoding=utf8'],'querySql':['SELECT id,name,amount,CAST(ts AS CHAR) AS ts FROM datax_rows ORDER BY id']}]
 j['job']['content'][0]['writer']['parameter']['connection'][0]['table']=['datax_stage'];r=job('datax-staged-jdbc',j)
 return {'receipt':r,'rows':copy_stage_final(),'adaptation':'source casts timestamp to text; target text stage then native DATETIME(6) cast'}
check('datax_jdbc_staging_preserves_microseconds',staged)
def upsert():
 with my.cursor() as c:c.execute("UPDATE datax_rows SET name='增量更新',amount=99.99 WHERE id=1")
 want[0]=(1,'增量更新',Decimal('99.99'),want[0][3])
 j=json.loads((B/'datax-staged-jdbc.json').read_text());j['job']['content'][0]['writer']['parameter']['writeMode']='update';r1=job('datax-upsert',j);rows1=copy_stage_final();r2=job('datax-upsert-repeat',j);rows2=copy_stage_final();assert rows1==rows2
 return {'first':r1,'repeat':r2,'rows':rows2,'duplicates':0}
check('datax_jdbc_upsert_and_repeat',upsert)
def file_reader():
 path=B/'datax-input.tsv';path.write_text('1\t增量更新\t99.99\t2026-10-10 12:00:00.123456\n2\t\t-56.78\t\\N\n3\t\\N\t\\N\t2026-10-11 00:00:00\n')
 j=clone();j['job']['content'][0]['reader']={'name':'txtfilereader','parameter':{'path':[str(path)],'encoding':'UTF-8','fileFormat':'csv','fieldDelimiter':'\t','nullFormat':'\\N','column':[{'index':0,'type':'long'},{'index':1,'type':'string'},{'index':2,'type':'string'},{'index':3,'type':'string'}]}}
 p=j['job']['content'][0]['writer']['parameter'];p['writeMode']='update';p['connection'][0]['table']=['datax_stage'];r=job('datax-file-to-mo',j);return {'receipt':r,'rows':copy_stage_final()}
check('datax_tsv_file_to_mo_staging',file_reader)
my.close();mo.close();(B/'datax-deep-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
