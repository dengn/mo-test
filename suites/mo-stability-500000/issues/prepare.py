import json
from pathlib import Path
P=Path('/workspace/mo-stability-500000/issues')
header="""### Is there an existing issue for the same bug?

- [x] I searched existing open and closed issues for this reproducer.

### Branch Name

main

### Commit ID

2726fb419b3afa1db2686ae1b2aaca563d1ae214

### Other Environment Information

Linux x86_64, 4 CPU quota / 32 GiB memory, a single local mo-service running LOG/TN/CN with DISK-V2 file services. Built with Go 1.27.1. All data and credentials below are synthetic local test fixtures.
"""
script=Path('/workspace/mo-stability-500000/index-race.py').read_text()
helper="""import pymysql,types
DB='index_race_repro_'+str(int(time.time()))
boot=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True,ssl_disabled=True)
with boot.cursor() as cur:cur.execute('create database '+DB)
boot.close()
def connect(engine='mo',timeout=20):
 c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=DB,autocommit=True,ssl_disabled=True,read_timeout=timeout)
 for sql in ['set experimental_hnsw_index=1','set experimental_fulltext2_index=1','set hnsw_threads_search=1','set probe_limit=128']:
  with c.cursor() as cur:cur.execute(sql)
 return c
def query(c,sql,params=None):
 with c.cursor() as cur:
  cur.execute(sql,params or None)
  return cur.fetchall() if cur.description else []
b=types.SimpleNamespace(connect=connect,query=query,norm=lambda x:x)
"""
script=script.replace("sys.path.insert(0,'/workspace/mo-cases-50000');import runner as b",helper).replace("P=Path('/workspace/mo-stability-500000');stop=","P=Path.cwd()/'index-race-output';P.mkdir(exist_ok=True);stop=")
script+="""\nc=connect(timeout=90)
for sql,params in [('show create table race_h',None),('insert into race_h values(%s,%s,%s)',[99000002,297000006,json.dumps([1.0]*64)]),('alter table race_h alter reindex ann hnsw force_sync',None)]:
 try:print('POST_LOAD',sql,query(c,sql,params))
 except Exception as e:print('POST_LOAD',sql,str(e))
c.close()
"""
index=header+"""
### Actual Behavior

Concurrent HNSW reindex and ordinary secondary-index CREATE/DROP leave persistent inconsistent index metadata. After the load stops, fresh sessions fail:

~~~text
INSERT / HNSW REINDEX:
ERROR 1146: no such table suite50_1791642084.__mo_index_secondary_01a127f5-a6f3-7253-8243-4948402df4f8

SHOW CREATE TABLE race_h:
ERROR 20101: internal error: missing visibility metadata for index "ridx_3" on table 380340
~~~

These errors survived a graceful service restart. Original HNSW reindex operations R011/R016/R021 failed; background writers accumulated 400 errors with code 1146. A secondary-index CREATE/DROP sequence also returned a duplicate-key error on internal __mo_%1_delete_rowid; the wrapper did not distinguish which of those two statements failed, so this is not attributed to CREATE alone.

No panic was observed. All 153 acknowledged writes across the four fixture tables were checked: 0 missing and 0 wrong values. The problem is persistent catalog consistency/table usability, not demonstrated acknowledged-write data loss.

### Expected Behavior

A conflicting DDL operation may be rejected cleanly, but a surviving table must not reference a dropped internal index table. INSERT, REINDEX and SHOW CREATE TABLE should work after the conflicting load ends.

### Steps to Reproduce

Install PyMySQL and run this standalone trigger reproducer against a dedicated local service on port 6001. It creates a fresh database, four tables with 500 seed rows each, HNSW/IVF/fulltext/fulltext2 indexes, 8 writers, 24 readers and up to 8 DDL workers (25 DDL operations).

The trigger is timing-sensitive. I have not established a deterministic two-session minimal trigger; the errors above are from the completed original run, not a claim that every execution must reproduce the race.

~~~python
"""+script+"""
~~~

### Additional information

Three fresh sequential controls (CREATE HNSW, CREATE secondary index, DROP secondary index, INSERT, HNSW REINDEX) passed. The affected table and raw records are retained. The code root cause has not been established.
"""
tls=Path('/workspace/mo-corners-50000/tls-coalescing-repro.py').read_text().replace('import socket,ssl,struct,time,json,concurrent.futures,collections','import socket,ssl,struct,time,json,concurrent.futures,collections,sys').replace("P=Path('/workspace/mo-corners-50000')","P=Path.cwd();CAFILE=sys.argv[1]").replace("str(P/'certs/ca.crt')","CAFILE")
tlsbody=header+"""
### Actual Behavior

Valid MySQL TLS connections hang during the SSLRequest-to-TLS transition. With the same SSLRequest, ClientHello and trusted certificate:

|Transport timing|Results|
|---|---|
|One sendall containing SSLRequest followed by ClientHello|40/40 handshake failures at the 2-second client timeout|
|Two sendall calls separated by 50 ms|40/40 successful TLS handshakes|

An additional ordinary PyMySQL probe failed on 6/30 serial and 57/100 concurrent valid TLS connections. The full TLS batch had 620 handshake failures among 4,000 positive configurations. Negative cases timing out before certificate verification were retained as unexpected transport failures, not counted as successful certificate rejection.

~~~text
_ssl.c:993: The handshake operation timed out
[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
~~~

The MemoryBIO reproducer stops after TLS negotiation, before MySQL authentication; it does not depend on PyMySQL's authentication logic.

### Expected Behavior

Receiving SSLRequest and ClientHello together should be equivalent to receiving them in separate TCP reads. A valid client must not require an artificial delay.

### Steps to Reproduce

Configure the local frontend with a locally CA-signed server certificate whose SAN includes localhost and 127.0.0.1:

~~~toml
[cn.frontend]
enableTls = true
tlsCaFile = "/path/to/ca.crt"
tlsCertFile = "/path/to/server.crt"
tlsKeyFile = "/path/to/server.key"
~~~

Run the script as: python tls_coalescing_repro.py /path/to/ca.crt.
PyMySQL is used only for protocol constants; TLS itself uses Python ssl.MemoryBIO. The client requires no private key.

~~~python
"""+tls+"""
~~~

### Additional information

Suspected root cause, not yet verified by a fix: mysql_buffer.go can pre-read ClientHello bytes after SSLRequest, while RawConn returns the underlying net.Conn. server.go passes RawConn directly to tls.Server, potentially bypassing bytes already buffered by Conn.

No panic, successful TLS downgrade or authorization bypass was observed.
"""
pub=header+"""
### Actual Behavior

The first CREATE PUBLICATION IF NOT EXISTS succeeds. Repeating the identical statement returns:

~~~text
ERROR 1062: Duplicate entry '(0,e2e_pub_idem)' for key '(account_id,pub_name)'
~~~

This also broke idempotent setup of the publish/subscribe test suite.

### Expected Behavior

IF NOT EXISTS should succeed as a no-op for an existing publication (optionally with a warning), retaining its definition. Ordinary CREATE without this clause may reject a duplicate.

### Steps to Reproduce

Connect as root in the sys account and execute ordinary SQL, not PREPARE:

~~~sql
CREATE DATABASE IF NOT EXISTS pub50;
CREATE TABLE IF NOT EXISTS pub50.visible
  (id BIGINT PRIMARY KEY, n BIGINT, label TEXT);
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
-- Unexpected ERROR 1062:
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
DROP PUBLICATION IF EXISTS e2e_pub_idem;
~~~

### Additional information

The separate restriction on preparing CREATE PUBLICATION is not involved. The AST contains IfNotExists, but I did not find its use in the create path in pkg/frontend/publication_subscription.go. Product code was not modified.
"""
task=header+"""
### Actual Behavior

CREATE TASK accepts a positive subsecond timeout, then stores it as zero and disables the execution deadline:

|Requested timeout|Stored timeout_seconds|Result|Rows committed|
|---|---:|---|---:|
|100ms|0|SUCCESS; about 2.37 seconds client wall time|1|
|1s|1|TIMEOUT; about 1.09 seconds client wall time|0|
|3s|3|SUCCESS|1|

All bodies use INSERT ... SELECT SLEEP(2). Ordinary task timeouts are not generally broken: the 1s control correctly timed out and rolled back.

The 1s error was ERROR 20101: context deadline exceeded / internal executor exec.

### Expected Behavior

A positive timeout must not silently turn into unlimited execution. If subsecond precision is unsupported, reject it clearly or retain a conservative nonzero bound. This reports silent disabling, rather than requiring nanosecond precision.

### Steps to Reproduce

~~~sql
CREATE DATABASE IF NOT EXISTS task_timeout_repro;
USE task_timeout_repro;
CREATE TABLE sink(kind INT, v INT);

CREATE TASK tt_100ms TIMEOUT '100ms'
  AS BEGIN INSERT INTO sink SELECT 0, SLEEP(2); END;
EXECUTE TASK tt_100ms;
SELECT COUNT(*) FROM sink WHERE kind=0; -- actual 1
SELECT timeout_seconds FROM mo_task.sql_task
  WHERE task_name='tt_100ms'; -- actual 0
SELECT status FROM mo_task.sql_task_run
  WHERE task_name='tt_100ms' ORDER BY run_id DESC LIMIT 1; -- SUCCESS

CREATE TASK tt_1s TIMEOUT '1s'
  AS BEGIN INSERT INTO sink SELECT 1, SLEEP(2); END;
EXECUTE TASK tt_1s; -- expected/actual deadline error
SELECT COUNT(*) FROM sink WHERE kind=1; -- actual 0
SELECT status FROM mo_task.sql_task_run
  WHERE task_name='tt_1s' ORDER BY run_id DESC LIMIT 1; -- TIMEOUT

CREATE TASK tt_3s TIMEOUT '3s'
  AS BEGIN INSERT INTO sink SELECT 2, SLEEP(2); END;
EXECUTE TASK tt_3s;
SELECT COUNT(*) FROM sink WHERE kind=2; -- actual 1

DROP TASK tt_100ms;
DROP TASK tt_1s;
DROP TASK tt_3s;
DROP TABLE sink;
DROP DATABASE task_timeout_repro;
~~~

### Additional information

ParseSQLTaskTimeout in pkg/taskservice/sql_task_utils.go accepts the duration and returns int(d / time.Second), so 100ms becomes 0. sql_task_executor.go only sets a deadline when TimeoutSeconds > 0.

The existing SQL regression uses 1s and expects TIMEOUT; that control passed here. Supporting or rejecting subsecond inputs is a policy choice, but silently accepting and disabling the bound is the reported behavior.
"""
items=[
 ('index','[Bug]: Concurrent HNSW reindex and secondary-index DDL leave persistent inconsistent index metadata',index),
 ('tls','[Bug]: TLS handshake hangs when MySQL SSLRequest and ClientHello arrive together',tlsbody),
 ('publication','[Bug]: CREATE PUBLICATION IF NOT EXISTS returns a duplicate-key error for an existing publication',pub),
 ('task','[Bug]: Positive SQL task timeouts below one second silently disable the execution deadline',task),
]
out=[]
for key,title,body in items:
 f=P/(key+'.md');f.write_text(body);out.append({'key':key,'title':title,'body_file':str(f),'body_bytes':f.stat().st_size})
(P/'planned-issues.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
