from runtime import *
import sqlalchemy as sa,warnings
out={'runtime_ref':REF,'correction':'Prior temporal comparison used strings of Python time vs timedelta; NUMERIC compared list vs tuple. Preserve original receipt; compare type semantics here.','cases':[]}
def clock(v):
 if v is None:return None
 if isinstance(v,datetime.timedelta):return (v.days*86400+v.seconds)*1000000+v.microseconds
 return (v.hour*3600+v.minute*60+v.second)*1000000+v.microsecond
for port in [6001,13306]:
 s=psql("SELECT id,clock,zoned AT TIME ZONE 'UTC',flag,day FROM eco4_temporal ORDER BY id");t=sql(port,'eco4','SELECT * FROM pg_temporal ORDER BY id')
 def norm(rows):return [(i,clock(c),z,None if f is None else bool(f),d) for i,c,z,f,d in rows]
 out['cases'].append({'case':'temporal_UTC_microseconds_boolean_date','port':port,'source':norm(s),'target':norm(t),'status':'passed' if norm(s)==norm(t) else 'failed'})
 s=psql('SELECT * FROM eco4_varnum ORDER BY id');t=sql(port,'eco4','SELECT * FROM pg_varnum ORDER BY id')
 out['cases'].append({'case':'unconstrained_NUMERIC_within_explicit_target38_18','port':port,'source':s,'target':t,'status':'passed' if list(s)==list(t) else 'failed'})
dump(B/'pg-extended-semantic-recheck.json',out);print(json.dumps(out,default=str,ensure_ascii=False))
metadata=[]
for port in [6001,13306]:
 sql(port,'eco4','CREATE TABLE IF NOT EXISTS bool_metadata4(id INT PRIMARY KEY,flag BOOL)')
 eng=sa.create_engine(f"mysql+pymysql://root:{'111' if port==6001 else 'types-local'}@127.0.0.1:{port}/eco4")
 with warnings.catch_warnings(record=True) as w:
  warnings.simplefilter('always');table=sa.Table('bool_metadata4',sa.MetaData(),autoload_with=eng)
 r={'port':port,'show_columns':sql(port,'eco4','SHOW COLUMNS FROM bool_metadata4'),'flag_type':str(table.c.flag.type),'warnings':[str(v.message) for v in w]}
 try:r['clone_DDL']=str(sa.schema.CreateTable(table.to_metadata(sa.MetaData(),name='bool_metadata_clone4')).compile(dialect=eng.dialect));r['status']='passed'
 except Exception as e:r['status']='failed';r['error']=str(e)
 metadata.append(r);eng.dispose()
dump(B/'boolean-reflection-result.json',{'runtime_ref':REF,'sqlalchemy_version':sa.__version__,'cases':metadata});print(json.dumps(metadata,default=str))
