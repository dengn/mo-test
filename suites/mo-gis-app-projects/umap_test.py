"""Real uMap HTTP login, map/layer edit, permissions, clone and MO remote-data link."""
import json
import re
import uuid
import requests
from common import *
BASE='http://127.0.0.1:18881'
LOG=[]

def session():
    s=requests.Session();s.trust_env=False;return s

def req(s,method,path,**kw):
    headers={'X-Requested-With':'XMLHttpRequest',**kw.pop('headers',{})}
    if method!='GET':headers.update({'X-CSRFToken':s.cookies.get('csrftoken',''),'Referer':BASE+'/en/'})
    r=s.request(method,BASE+path,headers=headers,timeout=30,**kw)
    LOG.append({'method':method,'path':path,'status':r.status_code,'body':r.text[:180000]})
    save('umap-http.json',LOG);return r

def login(name):
    s=session();r=req(s,'GET','/en/login/');assert r.status_code==200
    token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.text).group(1)
    r=req(s,'POST','/en/login/',data={'username':name,'password':'LocalGis2026!','csrfmiddlewaretoken':token},allow_redirects=True)
    assert 'sessionid' in s.cookies,(r.status_code,r.text[:1000]);return s

def run():
    owner=login('gisowner');other=login('gisoutsider')
    center={'type':'Point','coordinates':[116.31,39.81]}
    settings={'type':'Feature','geometry':center,'properties':{'name':'GIS 开源应用测试','description':'MO-backed remote geography; PostGIS uMap metadata',
        'zoom':12,'tilelayer':{'url_template':'http://127.0.0.1:18880/static/local-tile.png','minZoom':0,'maxZoom':22,'attribution':'Local synthetic grid'},
        'displayDataBrowserOnLoad':True,'miniMap':False,'moreControl':True}}
    data={'name':'GIS 开源应用测试','center':json.dumps(center),'settings':json.dumps(settings,ensure_ascii=False),'zoom':12}
    r=req(owner,'POST','/en/map/create/',data=data);assert r.status_code==200,r.text[:1000]
    created=r.json();mid=created['id']
    assert created['permissions']['owner']['name']=='gisowner',created
    # A normal uploaded point/line/polygon collection, including Unicode.
    fixtures=json.loads((P/'fixtures.json').read_text())
    import shapely
    local={'type':'FeatureCollection','features':[{'type':'Feature','geometry':shapely.geometry.mapping(shapely.from_wkt(w)),
             'properties':{'name':n}} for i,n,w in fixtures['mixed'][:3]],
           '_umap_options':{'name':'本地采集','displayOnLoad':True,'color':'DarkOrange','remoteData':{}}}
    layerid=str(uuid.uuid4())
    r=req(owner,'POST',f'/en/map/{mid}/datalayer/create/{layerid}/',data={'name':'本地采集','rank':0},
          files={'geojson':('local.geojson',json.dumps(local,ensure_ascii=False).encode(),'application/geo+json')})
    assert r.status_code==200,r.text[:1000]
    r=req(owner,'GET',f'/en/datalayer/{mid}/{layerid}/');assert r.status_code==200,r.text[:1000];assert len(r.json()['features'])==3
    # Actual application-supported remote GeoJSON data source backed by MO.
    remoteid=str(uuid.uuid4());url='http://127.0.0.1:18880/collections/mo-points/items?f=json&limit=500'
    remote={'type':'FeatureCollection','features':[],
            '_umap_options':{'name':'MO 实时点位','displayOnLoad':True,'color':'RoyalBlue','iconClass':'Circle',
                             'remoteData':{'url':url,'format':'geojson','dynamic':False,'proxy':False,'ttl':0}}}
    r=req(owner,'POST',f'/en/map/{mid}/datalayer/create/{remoteid}/',data={'name':'MO 实时点位','rank':1},
          files={'geojson':('remote.geojson',json.dumps(remote,ensure_ascii=False).encode(),'application/geo+json')})
    assert r.status_code==200,r.text[:1000]
    r=req(owner,'GET',f'/en/datalayer/{mid}/{remoteid}/');assert r.json()['_umap_options']['remoteData']['url']==url
    live=session().get(url,timeout=30).json();assert len(live['features'])==259
    # Owner can edit, unrelated user cannot; verify owner change persists.
    r=req(other,'POST',f'/en/map/{mid}/update/settings/',data=data);assert r.status_code==403,r.text[:1000]
    settings['properties']['description']='Edited through real uMap HTTP';data['settings']=json.dumps(settings,ensure_ascii=False)
    r=req(owner,'POST',f'/en/map/{mid}/update/settings/',data=data);assert r.status_code==200,r.text[:1000]
    # Public sharing and clone use the upstream permission and view handlers.
    r=req(owner,'POST',f'/en/map/{mid}/update/permissions/',data={'share_status':1,'edit_status':3,'owner':created['permissions']['owner']['id']})
    assert r.status_code==200,r.text[:1000]
    r=req(owner,'POST',f'/en/map/{mid}/update/clone/');assert r.status_code==200,r.text[:1000]
    clone=r.json();assert clone.get('redirect'),clone
    clone_id=int(clone['redirect'].rstrip('/').rsplit('_',1)[1]);assert clone_id!=mid,clone
    r=req(owner,'GET',clone['redirect']);assert r.status_code==200,r.text[:1000]
    r=req(owner,'GET',f'/map/{mid}/download/');assert r.status_code==200,r.text[:1000]
    backup=r.json();assert len(backup['layers'])==2,backup.keys()
    assert sum(len(layer.get('features',[])) for layer in backup['layers'])==3
    assert any(layer['_umap_options'].get('remoteData',{}).get('url')==url for layer in backup['layers'])
    save('umap-export.umap',backup)
    view=created.get('url') or f'/en/map/{mid}/'
    r=req(owner,'GET',view);assert r.status_code==200 and 'MO' in r.text
    save('umap-map-identifiers.json',{'map_id':mid,'local_layer':layerid,'remote_layer':remoteid,'clone':clone,'view_url':view,'remote_url':url,
                                     'clone_map_id':clone_id})
    return {'map_id':mid,'local_geometry_features':3,'remote_MO_features':259,'authenticated_create_edit':'pass',
            'outsider_edit_403':'pass','share_and_clone':'pass','metadata_backend':'PostGIS','GIS_remote_data_backend':'MatrixOne','view_url':view}

record('uMap','mo','login_map_layers_permissions_clone_live_MO',run,phase='hybrid_PostGIS_metadata_MO_data')
