import concurrent.futures
import json
from pathlib import Path
import urllib.request
import urllib.error

P=Path(__file__).resolve().parent
OUT=[]
def request(method,path,payload=None):
 data=json.dumps(payload).encode() if payload is not None else None
 q=urllib.request.Request('http://127.0.0.1:18189'+path,data=data,method=method,headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(q,timeout=20) as r:return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
for engine in ('mo','pg'):
 r={'engine':engine}
 try:
  status,data=request('GET',f'/api/{engine}/features');assert status==200 and len(data['features'])==3
  status,data=request('GET',f'/api/{engine}/nearby?lon=116.397&lat=39.908&radius=200');assert status==200 and [f['id'] for f in data['features']]==[1,2]
  f={'id':900001,'properties':{'label':"SQL quote ' and 中文"},'geometry':{'type':'Point','coordinates':[116.4,39.9]}}
  assert request('POST',f'/api/{engine}/features',f)[0]==200
  status,data=request('GET',f'/api/{engine}/features');got=next(x for x in data['features'] if x['id']==900001);assert got['properties']==f['properties']
  f['geometry']['coordinates']=[116.5,40.0];assert request('PUT',f'/api/{engine}/features',f)[0]==200
  assert request('DELETE',f'/api/{engine}/features',{'id':900001})[0]==200
  f['geometry']['coordinates']=[999,0];assert request('POST',f'/api/{engine}/features',f)[0]==400
  assert request('GET',f'/api/{engine}/nearby?lon=nan&lat=0&radius=1')[0]==400
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
   checks=list(ex.map(lambda _:request('GET',f'/api/{engine}/features'),range(64)))
  assert all(s==200 and len(d['features'])==3 for s,d in checks)
  r.update(status='pass',checks=['GeoJSON FeatureCollection','geodetic 200m search','prepared insert with quote/Unicode','update','delete','invalid coordinate rejection','nonfinite query rejection','64 concurrent reads'],concurrent_reads=64)
 except Exception as e:r.update(status='error',error=str(e))
 OUT.append(r)
(P/'http-results.json').write_text(json.dumps(OUT,indent=2));print(OUT)
