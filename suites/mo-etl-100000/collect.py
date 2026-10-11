import urllib.request,json,hashlib,concurrent.futures
from pathlib import Path
from html.parser import HTMLParser
P=Path(__file__).resolve().parent
urls={'snowflake': ['https://docs.snowflake.com/en/user-guide/data-load-overview','https://docs.snowflake.com/en/sql-reference/sql/copy-into-table','https://docs.snowflake.com/en/sql-reference/sql/copy-into-location','https://docs.snowflake.com/en/sql-reference/sql/merge','https://docs.snowflake.com/en/user-guide/data-load-transform','https://docs.snowflake.com/en/user-guide/streams-intro','https://docs.snowflake.com/en/sql-reference/constructs/qualify'], 'fivetran':['https://fivetran.com/docs/core-concepts/sync-modes','https://fivetran.com/docs/core-concepts/synced-data','https://fivetran.com/docs/core-concepts/column-blocking-and-hashing','https://fivetran.com/docs/core-concepts/schema','https://fivetran.com/docs/connectors/databases/mysql','https://fivetran.com/docs/connectors/files/csv'], 'dbt':['https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/incremental-models.md','https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/snapshots.md','https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/data-tests.md','https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/seeds.md','https://raw.githubusercontent.com/dbt-labs/docs.getdbt.com/current/website/docs/docs/build/sql-models.md','https://raw.githubusercontent.com/dbt-labs/dbt-core/main/README.md','https://raw.githubusercontent.com/fivetran/dbt_fivetran_utils/main/README.md']}
class Text(HTMLParser):
 def __init__(self):super().__init__();self.a=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['p','h1','h2','h3','pre','li','tr']:self.a.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.a.append(s)
def download(e,u):
 name=u.rsplit('/',1)[-1]+('.html' if not u.endswith('.md') else '');local=P/'sources'/e/name;local.parent.mkdir(parents=True,exist_ok=True)
 try:
  req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 MatrixOne ETL research'});r=urllib.request.urlopen(req,timeout=45);data=r.read();local.write_bytes(data)
  if not u.endswith('.md'):
   t=Text();t.feed(data.decode(errors='replace'));(local.with_suffix('.txt')).write_text(''.join(t.a))
  print('downloaded',e,u,len(data),flush=True);return dict(engine=e,url=u,local_path=str(local),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),source_id=e+':'+u,status='downloaded')
 except Exception as ex:print('failed',e,u,str(ex),flush=True);return dict(engine=e,url=u,status='failed',error=str(ex))
with concurrent.futures.ThreadPoolExecutor(6) as ex:m=list(ex.map(lambda x:download(*x),[(e,u) for e,v in urls.items() for u in v]))
(P/'source-manifest.json').write_text(json.dumps(m,indent=2))
