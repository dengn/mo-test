import pymysql,json,time
from pathlib import Path
B=Path(__file__).parent
deadline=time.monotonic()+90
while True:
 try:my=pymysql.connect(host='127.0.0.1',port=13306,user='root',password='etl-local',database='etl_source',autocommit=True);break
 except pymysql.MySQLError:
  if time.monotonic()>deadline:raise
  time.sleep(1)
with my:
 with my.cursor() as c:
  c.execute('SELECT version()');version=c.fetchone()[0]
  c.execute('DROP TABLE IF EXISTS accounts');c.execute('CREATE TABLE accounts(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),updated_at DATETIME(3)) CHARACTER SET utf8mb4')
  c.execute("INSERT INTO accounts VALUES(1,'Alice',12.34,'2026-10-10 10:00:00.123'),(2,'中文',56.78,'2026-10-10 11:00:00.456')")
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True) as mo:
 with mo.cursor() as c:
  c.execute('CREATE DATABASE IF NOT EXISTS etl_mysql_cdc');c.execute('DROP TABLE IF EXISTS etl_mysql_cdc.accounts');c.execute('CREATE TABLE etl_mysql_cdc.accounts(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),updated_at DATETIME(3))')
(B/'mysql-source-version.json').write_text(json.dumps({'version':version}));print(version)
