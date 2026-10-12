import pymysql,json
from pathlib import Path
B=Path(__file__).parent
out={'cases':[]}
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_batch',autocommit=True)
with d:
 with d.cursor() as c:
  c.execute("CREATE STAGE IF NOT EXISTS etl_s3 URL='s3://mo-test/etl-expanded/' CREDENTIALS={'aws_key_id'='minio','aws_secret_key'='minio123','aws_region'='us-east-1','endpoint'='http://127.0.0.1:9000','provider'='minio'}")
  for mode in ['local_explicit','s3_explicit','stage_explicit','stage_auto']:
   r={'name':mode}
   try:
    c.execute('DROP TABLE IF EXISTS compress_probe');c.execute('CREATE TABLE compress_probe LIKE s3_csv')
    if mode.startswith('local'):opts=f"'filepath'='{B}/rows.csv.gz','format'='csv','compression'='gzip'"
    elif mode.startswith('s3'):opts="'endpoint'='http://127.0.0.1:9000','region'='us-east-1','access_key_id'='minio','secret_access_key'='minio123','bucket'='mo-test','filepath'='etl-expanded/rows.csv.gz','provider'='minio','format'='csv','compression'='gzip'"
    else:opts="'filepath'='stage://etl_s3/rows.csv.gz','format'='csv'"+(",'compression'='gzip'" if mode.endswith('explicit') else '')
    sql=('LOAD DATA URL S3OPTION' if mode.startswith('s3') else 'LOAD DATA INFILE')+' {'+opts+'} INTO TABLE compress_probe FIELDS TERMINATED BY \',\' OPTIONALLY ENCLOSED BY \'"\' IGNORE 1 LINES'
    r['sql']=sql;c.execute(sql);c.execute('SELECT * FROM compress_probe ORDER BY id');got=c.fetchall();assert len(got)==3 and got[0][1]=='中文 😀' and got[1][1]=='' and got[2][1] is None;r.update(status='passed',rows=got)
   except Exception as e:r.update(status='failed',error=str(e))
   out['cases'].append(r);print(mode,r['status'],r.get('error',''),flush=True)
  c.execute('DROP STAGE etl_s3')
(B/'compression-control-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
