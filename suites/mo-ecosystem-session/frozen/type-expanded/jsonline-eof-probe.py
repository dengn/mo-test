import pymysql,json
from pathlib import Path
B=Path(__file__).parent;out={'cases':[]}
variants={
 'valid':'{"id":1,"v":{}}\n{"id":2,"v":{"a":1}}\n',
 'bare_malformed_last':'{"id":1,"v":{}}\nthis is not json\n',
 'incomplete_last':'{"id":1,"v":{}}\n{"id":2,"v":{"a":1}\n',
 'incomplete_only':'{"id":2,"v":{"a":1}\n',
 'incomplete_then_valid':'{"id":1,"v":{}}\n{"id":2,"v":{"a":1}\n{"id":3,"v":{}}\n',
 'malformed_closed':'{"id":1,"v":{}}\n{"id":2,"v":{invalid}}\n',
}
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='type_matrix',autocommit=True) as d,d.cursor() as c:
 c.execute('SELECT @@sql_mode');out['sql_mode']=c.fetchone()[0]
 for name,text in variants.items():
  p=B/('eof-'+name+'.jsonl');p.write_text(text);table='eof_'+name;c.execute('DROP TABLE IF EXISTS '+table);c.execute('CREATE TABLE '+table+'(id INT PRIMARY KEY,v JSON)');r={'name':name,'input':text}
  try:r['affected_rows']=c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {table}");r['load_status']='success'
  except pymysql.MySQLError as e:r.update(load_status='rejected',error=str(e))
  c.execute('SHOW WARNINGS');r['warnings']=c.fetchall();c.execute('SELECT id,v FROM '+table+' ORDER BY id');r['rows']=c.fetchall();c.execute('INSERT INTO '+table+" VALUES(100,'{}')");r['subsequent_write']='success'
  out['cases'].append(r);print(name,r['load_status'],r['rows'],flush=True)
 # Same final incomplete record with explicit error-column projection.
 p=B/'eof-incomplete_last.jsonl';c.execute('DROP TABLE IF EXISTS eof_error_source');c.execute(f"CREATE EXTERNAL TABLE eof_error_source(id INT,v JSON) INFILE{{'filepath'='{p}','format'='jsonline','jsondata'='object'}}")
 c.execute('SELECT id,v,__mo_file_line,__mo_error_message,__mo_error_text FROM eof_error_source');a=c.fetchall();assert len(a)==2 and a[1][3] is not None,a;out['explicit_error_mode']={'records':a,'reject_exposed':True}
(B/'jsonline-eof-result.json').write_text(json.dumps(out,indent=2,default=str))
