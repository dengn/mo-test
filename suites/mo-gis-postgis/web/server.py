"""Local GIS application API used by OpenLayers and HTTP workflow tests."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
import math
from pathlib import Path
import sys
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import connect,query

ROOT=Path(__file__).resolve().parent
def setup():
 for e in ('mo','pg'):
  c=connect(e)
  typ='point srid 4326' if e=='mo' else 'geometry(Point,4326)'
  query(c,f'create table if not exists web_places(id int primary key,label varchar(100),g {typ})')
  query(c,'delete from web_places')
  for i,label,x,y in [(1,'北京',116.397,39.908),(2,'附近点',116.398,39.909),(3,'上海',121.474,31.230)]:
   query(c,'insert into web_places values(%s,%s,st_geomfromtext(%s,4326))',(i,label,f'POINT({x} {y})'))
  c.close()

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,status,data):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  u=urlparse(self.path)
  if u.path.startswith('/api/'):
   try:
    parts=u.path.strip('/').split('/');e,op=parts[1:3]
    if e not in ('mo','pg'):raise ValueError('unknown engine')
    args=parse_qs(u.query);c=connect(e)
    sql='select id,label,st_asgeojson(g) from web_places';params=()
    if op=='nearby':
     x=float(args['lon'][0]);y=float(args['lat'][0]);r=float(args['radius'][0])
     if not all(map(math.isfinite,(x,y,r))) or not -180<=x<=180 or not -90<=y<=90 or r<0:raise ValueError('invalid coordinates/radius')
     ctor='st_geomfromtext(%s,4326)'
     dist='st_distance(g,'+ctor+')' if e=='mo' else 'st_distance(g::geography,('+ctor+')::geography,false)'
     sql+=' where '+dist+'<=%s';params=(f'POINT({x} {y})',r)
    elif op!='features':raise ValueError('unknown endpoint')
    rows=query(c,sql+' order by id',params if params else None);c.close()
    self.send(200,{'type':'FeatureCollection','features':[{'type':'Feature','id':i,'properties':{'label':label},'geometry':json.loads(g)} for i,label,g in rows]})
   except (ValueError,KeyError,IndexError) as ex:self.send(400,{'error':str(ex)})
   except Exception as ex:self.send(500,{'error':str(ex)})
   return
  filename='index.html' if u.path=='/' else u.path.lstrip('/')
  if filename not in ('index.html','bundle.js','bundle.css','style.css'):
   self.send(404,{'error':'not found'});return
  raw=(ROOT/filename).read_bytes();self.send_response(200);self.send_header('Content-Type','text/html' if filename.endswith('.html') else 'application/javascript' if filename.endswith('.js') else 'text/css');self.end_headers();self.wfile.write(raw)
 def do_POST(self):self.mutate('insert')
 def do_PUT(self):self.mutate('update')
 def do_DELETE(self):self.mutate('delete')
 def mutate(self,kind):
  try:
   parts=urlparse(self.path).path.strip('/').split('/');e=parts[1]
   if e not in ('mo','pg') or parts[2]!='features':raise ValueError('invalid endpoint')
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));i=int(data['id']);c=connect(e)
   if kind=='delete':query(c,'delete from web_places where id=%s',(i,))
   else:
    x,y=data['geometry']['coordinates'];x,y=float(x),float(y)
    if data['geometry']['type']!='Point' or not all(map(math.isfinite,(x,y))) or not -180<=x<=180 or not -90<=y<=90:raise ValueError('valid WGS84 Point required')
    label=str(data['properties']['label']);w=f'POINT({x} {y})'
    if kind=='insert':query(c,'insert into web_places values(%s,%s,st_geomfromtext(%s,4326))',(i,label,w))
    else:query(c,'update web_places set label=%s,g=st_geomfromtext(%s,4326) where id=%s',(label,w,i))
   c.close();self.send(200,{'ok':True,'id':i})
  except (ValueError,KeyError,TypeError,IndexError) as ex:self.send(400,{'error':str(ex)})
  except Exception as ex:self.send(500,{'error':str(ex)})

if __name__=='__main__':
 setup();print('GIS application on 127.0.0.1:18189',flush=True);ThreadingHTTPServer(('127.0.0.1',18189),Handler).serve_forever()
