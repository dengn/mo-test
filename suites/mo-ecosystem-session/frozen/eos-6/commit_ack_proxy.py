from runtime import *
import socketserver,socket,threading
guard=threading.Lock()
def frame(sock):
 def exact(n):
  chunks=[]
  while n:
   b=sock.recv(n)
   if not b:raise EOFError()
   chunks.append(b);n-=len(b)
  return b''.join(chunks)
 h=exact(4);return h+exact(int.from_bytes(h[:3],'little'))
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  client=self.request;backend=socket.create_connection(('127.0.0.1',6001),timeout=5);backend.settimeout(None);state={'commit':False}
  def forward_server():
   try:
    while True:
     data=frame(backend);payload=data[4:];drop=False
     with guard:
      if state['commit']:
       state['commit']=False
       if payload and payload[0]==0 and (B/'proxy-arm.json').exists():
        arm=json.loads((B/'proxy-arm.json').read_text());(B/'proxy-arm.json').unlink();drop=True
        dump(B/'proxy-commit-ack-dropped.json',{'case':arm,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'server_commit_response':'OK packet received from MO; suppressed before delivery to client','ok_payload_hex':payload.hex()})
     if drop:raise EOFError('injected loss of successful COMMIT acknowledgement')
     client.sendall(data)
   except (OSError,EOFError):
    for s in [client,backend]:
     try:s.shutdown(socket.SHUT_RDWR)
     except OSError:pass
  thread=threading.Thread(target=forward_server,daemon=True);thread.start()
  try:
   while True:
    data=frame(client);payload=data[4:]
    if payload[:1]==b'\x03' and payload[1:].strip().upper()==b'COMMIT':
     with guard:state['commit']=True
    backend.sendall(data)
  except (OSError,EOFError):pass
  finally:backend.close();client.close()
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
with Server(('127.0.0.1',16001),Handler) as server:
 print('PROXY READY local-only 16001 -> 6001',flush=True);server.serve_forever()
