"""Minimal native SQL reproduction of Airbyte MO destination blocker #29849."""
from runtime import *
if __name__=='__main__':
 verify_ownership()
 p=B/'load-repro.tsv';p.write_text('1\talpha\n2\tNULL\n')
 receipts=[]
 for role in [6001,13306]:
  with db(role,local_infile=True) as d,d.cursor() as c:
   c.execute('CREATE TABLE IF NOT EXISTS airbyte_load_repro(id BIGINT,v VARCHAR(32))')
   for repeat in range(3):
    c.execute('DELETE FROM airbyte_load_repro')
    q="LOAD DATA LOCAL INFILE %s INTO TABLE airbyte_load_repro FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' (id,@v) SET v=NULLIF(@v,'NULL')"
    row={'logical_endpoint':role,'repeat':repeat,'sql':q,'fixture':p.read_text(),'expected':[[1,'alpha'],[2,None]]}
    try:
     c.execute(q,(str(p),));c.execute('SELECT id,v FROM airbyte_load_repro ORDER BY id')
     actual=[list(x) for x in c.fetchall()]
     row.update(status='passed' if actual==row['expected'] else 'fidelity_failed',actual=actual)
    except Exception as e:row.update(status='execution_failed',error=str(e))
    receipts.append(row)
 dump(B/'load-repro-receipt.json',receipts)
 print([(r['logical_endpoint'],r['repeat'],r['status']) for r in receipts])
