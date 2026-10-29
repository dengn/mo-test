"""Native table scan: independently seeded MySQL source -> native engine -> both SQL sinks."""
import os,sys,json,time,traceback,collections,hashlib
from pathlib import Path
D=Path(__file__).parent; B=D.parent
sys.path.insert(0,'/workspace/toolchains/python/lib/python3.12/site-packages')
sys.path.insert(0,str(B/'windowed'));sys.path.insert(0,str(D))
import guard_5g;guard_5g.install()
import heavy as h, native_batch as nb
from recycle_profile import register,archive_profile
nb.h=h
tool=sys.argv[1];assert tool in ['dataxscan','sparkscan']
inventory=json.loads((D/'java-runtime-inventory.json').read_text())
home=inventory['jre8' if tool=='dataxscan' else 'jre17']['home']
os.environ['JAVA_HOME']=home;os.environ['PATH']=home+'/bin:'+os.environ['PATH']
os.environ['PYSPARK_SUBMIT_ARGS']='--driver-memory 512m pyspark-shell'
out=D/(tool+'-results.jsonl');assert not out.exists(),'Immutable run already exists'
profiles=['int64','uint64','decimal38_18','decimal65_30','varchar_utf8','varbinary','datetime6','time6']
raw_profiles=['uint64','datetime6','time6'] if tool=='dataxscan' else ['decimal38_18','decimal65_30','datetime6','time6']
records=[]
try:
 for pi,name in enumerate(profiles):
  p=next(x for x in h.PROFILES if x['name']==name);h.guard()
  t,s=h.tables(tool,p);source='e_'+tool+'_'+name
  for role in [6001,13306]:
   for table in [t,s,source]:
    h.sql('CREATE TABLE '+table+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(8192),rev BIGINT,PRIMARY KEY(case_id,id))',port=role)
    register(role,table,tool,name)
  profile_records=[]
  for mi,mode in enumerate((['raw'] if name in raw_profiles else [])+['text_adapter']):
   cid=100001+pi*4+mi;rows=h.base_rows(cid,p,4) # 256 rows, Unicode labels about 8KiB each
   with h.db(13306,autocommit=False) as db,db.cursor() as c:
    c.executemany('INSERT INTO '+source+' VALUES(%s,%s,%s,%s,%s)',rows);db.commit()
   src=h.sql('SELECT case_id,id,v,label,rev FROM '+source+' WHERE case_id=%s ORDER BY id',(cid,),port=13306)
   expected=h.canon(rows,p);assert h.canon(src,p)==expected,'Source fixture changed before ETL'
   value='v' if mode=='raw' else "REPLACE(TO_BASE64(v),CHAR(10),'')" if name=='varbinary' else 'CAST(v AS CHAR CHARACTER SET utf8mb4)'
   query='SELECT case_id,id,'+value+' AS v,label,rev FROM '+source+' WHERE case_id='+str(cid)
   os.environ['MO_DATAX_ACTUAL_QUERY']=query
   if mode=='raw':os.environ['MO_DATAX_RAW_READ']='1'
   else:os.environ.pop('MO_DATAX_RAW_READ',None)
   frame=None;read_error=None
   if tool=='sparkscan':
    try:
     from pyspark.sql import SparkSession,functions as F
     if nb.SPARK is None:
      scratch=D/'spark-scan-runtime';scratch.mkdir(exist_ok=True)
      os.environ['SPARK_LOCAL_DIRS']=str(scratch);os.environ['SPARK_LOCAL_IP']='127.0.0.1'
      nb.SPARK=(SparkSession.builder.master('local[2]').appName('owned-real-source-scan')
       .config('spark.ui.enabled','false').config('spark.jars',str(nb.JDBC))
       .config('spark.sql.session.timeZone','UTC').config('spark.sql.shuffle.partitions','2')
       .config('spark.task.maxFailures','1').config('spark.sql.warehouse.dir',str(scratch/'warehouse')).getOrCreate())
      nb.SPARK.sparkContext.setLogLevel('ERROR')
     e=h.endpoint(13306)
     frame=(nb.SPARK.read.format('jdbc').option('url',h.jdbc_url(13306)).option('dbtable','('+query+') fixture')
      .option('user',e['user']).option('password',e['password']).option('driver','com.mysql.cj.jdbc.Driver')
      .option('partitionColumn','id').option('lowerBound','0').option('upperBound',str(len(rows)))
      .option('numPartitions','2').option('fetchsize','17').load().filter('id >= 0'))
     if name=='varbinary' and mode!='raw':frame=frame.withColumn('v',F.unbase64('v'))
    except Exception as ex:read_error=ex
   for role in [6001,13306]:
    h.guard();start=time.monotonic()
    r={'id':f'{tool}_{name}_{mode}_{role}','tool':tool,'profile':name,'mode':mode,'role':role,
       'source_endpoint':23306,'target_endpoint':h.endpoint(role)['port'],'rows':len(rows),'logical_case_id':cid,
       'source_oracle_sha256':h.sha(expected),'expected_sha256':h.sha(expected),
       'path':'real MySQL table -> DataX mysqlreader/Groovy/mysqlwriter' if tool=='dataxscan' else 'real MySQL table -> Spark JDBC reader/filter/two writer partitions',
       'native_partitions':1 if tool=='dataxscan' else 2,'batch_size':17,'source_table':source,'target_table':t}
    try:
     if read_error:raise read_error
     if tool=='dataxscan':nb.datax_load(p,t,rows,role,r['id'],None)
     else:
      e=h.endpoint(role);r['spark_schema']=frame.schema.jsonValue()
      (frame.repartition(2).write.format('jdbc').mode('append').option('url',h.jdbc_url(role))
       .option('dbtable',t).option('driver','com.mysql.cj.jdbc.Driver').option('user',e['user'])
       .option('password',e['password']).option('batchsize','17').option('numPartitions','2')
       .option('isolationLevel','READ_COMMITTED').save())
     actual=h.sql('SELECT case_id,id,v,label,rev FROM '+t+' WHERE case_id=%s ORDER BY id',(cid,),port=role)
     a=h.canon(actual,p);r.update(actual_rows=len(a),actual_sha256=h.sha(a),status='passed' if a==expected else 'fidelity_failed')
     if a!=expected:r['first_mismatches']=[{'expected':e[:3]+[e[3][:80],e[4]],'actual':v[:3]+[v[3][:80],v[4]]} for e,v in zip(expected,a) if e!=v][:3]
    except Exception as ex:r.update(status='execution_failed',error_type=type(ex).__name__,error=nb.scrub(str(ex))[-2400:])
    r['elapsed_s']=time.monotonic()-start
    # A separate DB connection repeats the complete target read; failed side effects are retained.
    a=h.canon(h.sql('SELECT case_id,id,v,label,rev FROM '+t+' WHERE case_id=%s ORDER BY id',(cid,),port=role),p)
    r['fresh_readback_sha256']=h.sha(a);r['fresh_readback_rows']=len(a)
    if r['status']=='passed':assert h.sha(a)==r['expected_sha256']
    with out.open('a') as f:f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
    records.append(r);profile_records.append(r);print('REAL_SCAN',r['id'],r['status'],flush=True)
  receipt=archive_profile(tool,name,apply=True);receipt['case_ids']=[r['id'] for r in profile_records]
  h.dump(Path(receipt['archive']).with_suffix('.receipt.json'),receipt)
finally:
 if nb.SPARK is not None:nb.SPARK.stop()
 h.dump(D/(tool+'-summary.json'),{'cases':len(records),'counts':dict(collections.Counter(r['status'] for r in records)),
  'scope':'Native table scan + native batched write, 256 rows per case; explicit text/Base64 variants. No CDC, deletes, EOS or disk throughput claim.'})
