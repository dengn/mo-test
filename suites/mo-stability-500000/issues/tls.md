### Is there an existing issue for the same bug?

- [x] I searched existing open and closed issues for this reproducer.

### Branch Name

main

### Commit ID

2726fb419b3afa1db2686ae1b2aaca563d1ae214

### Other Environment Information

Linux x86_64, 4 CPU quota / 32 GiB memory, a single local mo-service running LOG/TN/CN with DISK-V2 file services. Built with Go 1.27.1. All data and credentials below are synthetic local test fixtures.

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
import socket,ssl,struct,time,json,concurrent.futures,collections,sys
from pathlib import Path
from pymysql.constants import CLIENT
P=Path.cwd();CAFILE=sys.argv[1]
def readall(s,n):
 b=b''
 while len(b)<n:
  x=s.recv(n-len(b))
  if not x:raise EOFError('peer closed')
  b+=x
 return b
def one(mode,i):
 s=None;t=time.monotonic();status='pass';err=None
 try:
  s=socket.create_connection(('127.0.0.1',6001),timeout=2);h=readall(s,4);readall(s,int.from_bytes(h[:3],'little'))
  ib,ob=ssl.MemoryBIO(),ssl.MemoryBIO();ctx=ssl.create_default_context(cafile=CAFILE);tls=ctx.wrap_bio(ib,ob,server_hostname='localhost')
  try:tls.do_handshake()
  except ssl.SSLWantReadError:pass
  hello=ob.read();flags=CLIENT.PROTOCOL_41|CLIENT.SSL|CLIENT.SECURE_CONNECTION|CLIENT.LONG_PASSWORD|CLIENT.LONG_FLAG|CLIENT.TRANSACTIONS;payload=struct.pack('<IIB23s',flags,16777216,45,b'');packet=len(payload).to_bytes(3,'little')+b'\x01'+payload
  if mode=='coalesced':s.sendall(packet+hello)
  else:s.sendall(packet);time.sleep(.05);s.sendall(hello)
  while True:
   try:tls.do_handshake();break
   except ssl.SSLWantReadError:
    outgoing=ob.read()
    if outgoing:s.sendall(outgoing)
    incoming=s.recv(65536)
    if not incoming:raise EOFError('server closed before TLS completion')
    ib.write(incoming)
  final=ob.read()
  if final:s.sendall(final)
 except Exception as e:status='handshake_failed';err=str(e)
 finally:
  if s:s.close()
 return {'mode':mode,'id':i,'status':status,'error':err,'seconds':time.monotonic()-t}
rows=[]
for mode in ['coalesced','separated']:
 with concurrent.futures.ThreadPoolExecutor(8) as ex:r=list(ex.map(lambda i:one(mode,i),range(40)))
 rows+=r;print(mode,collections.Counter(x['status'] for x in r),flush=True)
(P/'tls-coalescing-repro.json').write_text(json.dumps(rows,indent=2))

~~~

### Additional information

Suspected root cause, not yet verified by a fix: mysql_buffer.go can pre-read ClientHello bytes after SSLRequest, while RawConn returns the underlying net.Conn. server.go passes RawConn directly to tls.Server, potentially bypassing bytes already buffered by Conn.

No panic, successful TLS downgrade or authorization bypass was observed.
