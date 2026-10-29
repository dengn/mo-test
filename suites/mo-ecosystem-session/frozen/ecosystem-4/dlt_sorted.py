from runtime import *
import dlt,traceback
from dlt.destinations import sqlalchemy
from dlt.sources.sql_database import sql_table
import datetime as dt
os.environ['DLT_TELEMETRY']='false'
out={'runtime_ref':REF,'tool':'dlt '+dlt.__version__,'scope':'official sqlalchemy destination; full extract/normalize/load pipeline and MySQL independent controls','cases':[]}
hints={'id':{'data_type':'bigint','nullable':False,'dedup_sort':'asc'},'signed':{'data_type':'bigint'},'amount':{'data_type':'decimal','precision':38,'scale':18},'payload':{'data_type':'binary'},'name':{'data_type':'text'},'ts':{'data_type':'timestamp','precision':6,'timezone':False},'doc':{'data_type':'json'},'uuid_text':{'data_type':'text'}}
rows=[{'id':1,'signed':9007199254740993,'amount':decimal.Decimal('12345678901234567890.123456789012345678'),'payload':b'\x00\xff\x80','name':'dlt中文😀','ts':dt.datetime(2026,10,11,12,0,0,123456),'doc':{'big':9007199254740993,'nested':[None,True,'']},'uuid_text':'550e8400-e29b-41d4-a716-446655440000'},
 {'id':2,'signed':-9223372036854775808,'amount':decimal.Decimal('-0.000000000000000001'),'payload':b'\x01','name':'','ts':dt.datetime(2026,10,11,0,0,0),'doc':[],'uuid_text':''},
 {'id':3,'signed':None,'amount':None,'payload':None,'name':None,'ts':None,'doc':None,'uuid_text':None}]
for port in [13306,6001]:
 ds='eco4_dlt_sorted_'+str(port);pipeline=dlt.pipeline(pipeline_name=ds,pipelines_dir=str(B/'dlt-state'),destination=sqlalchemy(credentials=f"mysql+pymysql://root:{'111' if port==6001 else 'types-local'}@127.0.0.1:{port}/eco4"),dataset_name=ds)
 for mode in ['initial','merge_update','merge_delete','schema_add']:
  r={'port':port,'case':mode,'dataset':ds}
  try:
   if mode=='initial':data=rows;info=pipeline.run(data,table_name='records',write_disposition='append',columns=hints)
   elif mode=='merge_update':
    data=[dict(rows[0],name='dlt更新😀',amount=decimal.Decimal('0.000000000000000123')),dict(rows[1]),dict(rows[2]),dict(rows[0],id=4,name='new')];info=pipeline.run(data,table_name='records',write_disposition='merge',primary_key='id',columns=hints)
   elif mode=='merge_delete':
    hh=dict(hints,deleted={'data_type':'bool','hard_delete':True});data=[dict(rows[0],deleted=True)];info=pipeline.run(data,table_name='records',write_disposition='merge',primary_key='id',columns=hh)
   else:
    data=[dict(rows[1],added_tag='演进😀')];info=pipeline.run(data,table_name='records',write_disposition='merge',primary_key='id',columns=dict(hints,added_tag={'data_type':'text'}))
   r['load_info']=str(info);cols='id,signed,CAST(amount AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,uuid_text';r['target_rows']=sql(port,ds,'SELECT '+cols+' FROM records ORDER BY id');r['status']='completed'
  except Exception as e:r['status']='failed';r['error']=str(e);r['traceback']=traceback.format_exc();print(port,mode,str(e)[-1000:],flush=True)
  out['cases'].append(r);dump(B/'dlt-sorted-result.json',out);print('DLT',port,mode,r['status'],flush=True)
  if r['status']=='failed':break
dump(B/'dlt-sorted-result.json',out)
