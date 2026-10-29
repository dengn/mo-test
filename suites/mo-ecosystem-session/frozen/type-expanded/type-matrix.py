import csv,datetime,json,struct,traceback,math
from decimal import Decimal
from pathlib import Path
import pymysql,pyarrow as pa,pyarrow.parquet as pq
B=Path(__file__).parent
cases=[]
def add(name,ddl,values,arrow,family='plain',query='v'):cases.append(dict(name=name,ddl=ddl,values=values,arrow=arrow,family=family,query=query))
for n,bits in [('tiny',8),('small',16),('int',32),('big',64)]:
 ddl={'tiny':'TINYINT','small':'SMALLINT','int':'INT','big':'BIGINT'}[n]
 add(n+'_signed',ddl,[-2**(bits-1),0,2**(bits-1)-1,None],getattr(pa,'int'+str(bits))())
 add(n+'_unsigned',ddl+' UNSIGNED',[0,2**bits-1,None],getattr(pa,'uint'+str(bits))())
add('decimal38_0','DECIMAL(38,0)',[Decimal('99999999999999999999999999999999999999'),Decimal('-99999999999999999999999999999999999999'),Decimal('9007199254740993'),None],pa.decimal128(38,0))
add('decimal38_18','DECIMAL(38,18)',[Decimal('12345678901234567890.123456789012345678'),Decimal('-12345678901234567890.123456789012345678'),Decimal('0.000000000000000001'),None],pa.decimal128(38,18))
add('decimal38_38','DECIMAL(38,38)',[Decimal('0.99999999999999999999999999999999999999'),Decimal('-0.99999999999999999999999999999999999999'),None],pa.decimal128(38,38))
add('float32','FLOAT',[1.401298464324817e-45,3.4028234663852886e38,-123.125,None],pa.float32(),'float32')
add('float64','DOUBLE',[5e-324,1.7976931348623157e308,-1.2345678901234567,None],pa.float64(),'float64')
add('bool_type','BOOL',[True,False,None],pa.bool_(),'bool')
add('utf8_control','VARCHAR(500)',['中文 😀 e\u0301\n\t"\\', '', '\x00inside',None],pa.string())
add('bytes_raw','VARBINARY(50)',[b'\x00\xff\x80abc',b'',b'\x00',None],pa.binary(),'bytes')
add('blob_raw','BLOB',[b'\x00\xff\x80abc',b'',None],pa.binary(),'bytes')
add('date_bounds','DATE',[datetime.date(1000,1,1),datetime.date(2024,2,29),datetime.date(9999,12,31),None],pa.date32(),'date')
add('datetime_bounds','DATETIME(6)',[datetime.datetime(1000,1,1),datetime.datetime(2024,2,29,23,59,59,123456),datetime.datetime(9999,12,31,23,59,59,999999),None],pa.timestamp('us'),'datetime')
add('timestamp_us','TIMESTAMP(6)',[datetime.datetime(1971,1,1,1,2,3,123456),datetime.datetime(2026,10,10,16,0,0,654321),None],pa.timestamp('us'),'datetime')
add('clock_us','TIME(6)',[datetime.time(0,0),datetime.time(23,59,59,999999),None],pa.time64('us'),'time')
add('duration_time','TIME(6)',[datetime.timedelta(microseconds=-3020399999999),datetime.timedelta(microseconds=3020399999999),datetime.timedelta(microseconds=-1),None],pa.duration('us'),'time')
add('json_rich','JSON',[{'i':9007199254740993,'u':18446744073709551615,'nested':[True,None,{'中文':'😀'}]},[],{},None],pa.string(),'json')
add('uuid_type','UUID',['00000000-0000-0000-0000-000000000000','ffffffff-ffff-ffff-ffff-ffffffffffff',None],pa.string())
add('enum_type',"ENUM('red','中文','')",['red','中文','',None],pa.string())
add('set_type',"SET('a','中文')",['','a','a,中文',None],pa.string())
add('vector32','VECF32(3)',[[1.25,-2.5,3.75],[0,0,0],None],pa.list_(pa.float32()),'vector')
add('vector64','VECF64(3)',[[1.2345678901234567,-2.5,3.75],[0,0,0],None],pa.list_(pa.float64()),'vector')
add('bit64','BIT(64)',[0,18446744073709551615,None],pa.uint64(),query='CAST(v AS UNSIGNED)')

def normalized(v,family):
 if v is None:return None
 if family=='json':return v if isinstance(v,(dict,list)) else json.loads(v)
 if family=='vector':return v if isinstance(v,list) else json.loads(v)
 if family=='bytes':return bytes(v).hex()
 if family=='bool':return bool(v)
 if family=='time':
  if isinstance(v,datetime.time):return (v.hour*3600+v.minute*60+v.second)*1000000+v.microsecond
  if isinstance(v,datetime.timedelta):return (v.days*86400+v.seconds)*1000000+v.microseconds
 if family=='float32':return struct.pack('!f',float(v)).hex()
 if family=='float64':return struct.pack('!d',float(v)).hex()
 if isinstance(v,Decimal):return str(v)
 if isinstance(v,(datetime.datetime,datetime.date)):return v.isoformat()
 return v
def text(v,family):
 if v is None:return None
 if family in ['json','vector']:return json.dumps(v,ensure_ascii=False,separators=(',',':'))
 if isinstance(v,datetime.timedelta):
  u=normalized(v,'time');sign='-' if u<0 else '';u=abs(u);return f'{sign}{u//3600000000:02}:{u//60000000%60:02}:{u//1000000%60:02}.{u%1000000:06}'
 if isinstance(v,(datetime.time,datetime.datetime,datetime.date)):return str(v)
 return str(v)
def oracle(d,table,case):
 with d.cursor() as c:c.execute(f'SELECT {case["query"]} FROM {table} ORDER BY id');got=[normalized(r[0],case['family']) for r in c.fetchall()]
 want=[normalized(v,case['family']) for v in case['values']]
 assert got==want,{'actual':got,'expected':want};return {'actual':got,'expected':want}
def run(port=6001,password='111',engine='matrixone',routes=None):
 routes=routes or ['dbapi','csv','jsonline','parquet','arrow']
 out={'engine':engine,'runtime_ref':'652c643666428f1c434e03369834f2a9bead7c27','cases':[]}
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,autocommit=True,binary_prefix=True)
 try:
  with d.cursor() as c:c.execute('CREATE DATABASE IF NOT EXISTS type_matrix');c.execute('USE type_matrix');c.execute("SET time_zone='+00:00'")
  for case in cases:
   name=case['name'];vals=case['values'];family=case['family']
   for route in routes:
    if route in ['csv','jsonline'] and family=='bytes':continue
    r={'name':name,'ddl':case['ddl'],'route':route};table=name+'_'+route
    try:
     with d.cursor() as c:
      c.execute('DROP TABLE IF EXISTS '+table);c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v {case["ddl"]})')
      if route=='dbapi':
       data=[(i+1,text(v,family) if family in ['json','vector'] or isinstance(v,datetime.time) else v) for i,v in enumerate(vals)]
       c.executemany('INSERT INTO '+table+' VALUES(%s,%s)',data)
      elif route=='csv':
       p=B/(name+'.csv')
       with p.open('w',newline='') as f:csv.writer(f,quoting=csv.QUOTE_ALL).writerows([(i+1,text(v,family) if v is not None else '\\N') for i,v in enumerate(vals)])
       c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='csv'}} INTO TABLE {table} FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"'")
      elif route=='jsonline':
       p=B/(name+'.jsonl');p.write_text(''.join(json.dumps({'id':i+1,'v':v if family in ['json','vector','bool'] or isinstance(v,int) else text(v,family)},ensure_ascii=False)+'\n' for i,v in enumerate(vals)))
       c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {table}")
      else:
       av=[text(v,family) if family=='json' and v is not None else v for v in vals]
       t=pa.table({'id':pa.array(range(1,len(vals)+1),pa.int32()),'v':pa.array(av,case['arrow'])});p=B/(name+'.'+route)
       if route=='parquet':pq.write_table(t,p)
       else:
        with pa.OSFile(str(p),'wb') as f:
         with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
       c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{route}'}} INTO TABLE {table}")
     r['evidence']=oracle(d,table,case);r['status']='passed'
    except Exception as e:
     r.update(status='failed',error=str(e))
     with d.cursor() as c:
      try:c.execute('SELECT count(*) FROM '+table);r['rows_after_failure']=c.fetchone()[0]
      except Exception:pass
    out['cases'].append(r);print(engine,name,route,r['status'],r.get('error','')[:200],flush=True)
  return out
 finally:d.close()
if __name__=='__main__':
 r=run();(B/'type-matrix-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,default=str));print('CASES',len(r['cases']),'PASS',sum(x['status']=='passed' for x in r['cases']))
