"""Test adapter: serve Nessie LoadTable vended config through /credentials.

Nessie 0.107.3 /credentials returns HTTP 500/NullPointerException locally.
Other routes are forwarded unchanged; schema, manifests and data are real.
This adapter is explicitly recorded as a limitation of the local fixture.
"""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import requests,json
class H(BaseHTTPRequestHandler):
 def go(self):
  path=self.path;headers={k:v for k,v in self.headers.items() if k.lower() not in ['host','content-length','connection','accept-encoding']};body=self.rfile.read(int(self.headers.get('Content-Length',0))) or None
  if self.command=='GET' and path.split('?')[0].endswith('/credentials'):
   target=path.split('?')[0][:-12];headers['X-Iceberg-Access-Delegation']='vended-credentials'
   r=requests.get('http://127.0.0.1:19120'+target,headers=headers,timeout=20)
   if r.status_code==200:
    j=r.json();cfg=j.get('config',{});cfg['s3.region']=cfg.get('client.region','us-east-1');j={'storage-credentials':[{'prefix':'s3://mo-iceberg/warehouse','config':cfg}]};data=json.dumps(j).encode();status=200
   else:data=r.content;status=r.status_code
  else:
   r=requests.request(self.command,'http://127.0.0.1:19120'+path,headers=headers,data=body,timeout=30);status=r.status_code;data=r.content
   if 'json' in r.headers.get('Content-Type',''):
    data=data.replace(b'127.0.0.1:19120',b'127.0.0.1:19122')
  self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 do_GET=go;do_POST=go;do_DELETE=go;do_HEAD=go;do_PUT=go
 def log_message(self,fmt,*a):print(fmt%a,flush=True)
ThreadingHTTPServer(('127.0.0.1',19122),H).serve_forever()
