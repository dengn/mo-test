import socket,ssl,struct,time,json,concurrent.futures,collections
from pathlib import Path
from pymysql.constants import CLIENT
P=Path('/workspace/mo-corners-50000')
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
  ib,ob=ssl.MemoryBIO(),ssl.MemoryBIO();ctx=ssl.create_default_context(cafile=str(P/'certs/ca.crt'));tls=ctx.wrap_bio(ib,ob,server_hostname='localhost')
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
