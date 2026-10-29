# Reviewable restore companion for the prepared archive; does not execute unless called explicitly.
from runtime import *
import gzip,argparse
P=argparse.ArgumentParser();P.add_argument('--table',required=True);a=P.parse_args();receipt=json.loads((B/'mysql-archive-ownership.json').read_text());assert a.table in {r['table'] for r in receipt['tables']}
def decode(v):
 if not isinstance(v,dict) or 'kind' not in v:return v
 k=v['kind'];x=v['value']
 return {'decimal':lambda:decimal.Decimal(x),'datetime':lambda:datetime.datetime.fromisoformat(x),'date':lambda:datetime.date.fromisoformat(x),'duration':lambda:datetime.timedelta(microseconds=x),'bytes':lambda:bytes.fromhex(x),'set':lambda:','.join(x)}[k]()
rows=[];ddl=None;columns=None
with gzip.open(B/receipt['file'],'rt',encoding='utf8') as f:
 for line in f:
  x=json.loads(line)
  if x.get('name')==a.table:ddl=x['ddl'];columns=x['columns']
  if x.get('table')==a.table:rows.append([decode(v) for v in x['row']])
assert ddl and columns
with db(13306,autocommit=False) as d,d.cursor() as c:
 # Only append into empty, allowlisted target; never drop an existing table/data.
 c.execute(ddl.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1));c.execute('SELECT COUNT(*) FROM `'+a.table+'`');assert c.fetchone()[0]==0,'refuses to overwrite existing rows'
 q='INSERT INTO `'+a.table+'`('+','.join('`'+v+'`' for v in columns)+') VALUES('+','.join(['%s']*len(columns))+')'
 for i in range(0,len(rows),50):c.executemany(q,rows[i:i+50])
 d.commit()
print('RESTORED',a.table,len(rows))
