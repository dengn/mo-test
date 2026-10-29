import pymysql,json,pathlib,datetime
B=pathlib.Path(__file__).resolve().parent;p=B/'load-repro.tsv';p.write_text('1\talpha\n2\tNULL\n');out=[]
for port,password in [(6001,'111'),(13306,'types-local')]:
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,database='orchestrator10000',autocommit=True,local_infile=True,read_timeout=60)
 with d.cursor() as c:
  c.execute('CREATE TABLE IF NOT EXISTS airbyte_load_repro(id BIGINT,v VARCHAR(32))')
  for repeat in range(3):
   c.execute('DELETE FROM airbyte_load_repro');q="LOAD DATA LOCAL INFILE %s INTO TABLE airbyte_load_repro FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' (id,@v) SET v=NULLIF(@v,'NULL')";r={'port':port,'repeat':repeat,'sql':q,'fixture':p.read_text(),'expected':[[1,'alpha'],[2,None]]}
   try:c.execute(q,(str(p),));c.execute('SELECT id,v FROM airbyte_load_repro ORDER BY id');actual=[list(x) for x in c.fetchall()];r.update(status='passed' if actual==r['expected'] else 'fidelity_failed',actual=actual)
   except Exception as e:r.update(status='execution_failed',error=str(e))
   out.append(r)
 d.close()
(B/'load-repro-receipt.json').write_text(json.dumps(out,indent=2));print([(r['port'],r['repeat'],r['status'],r.get('error')) for r in out],flush=True)
