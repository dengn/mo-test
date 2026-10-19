"""Actual OGC API discovery, geometry fidelity, filtering, CRUD and mixed HTTP load."""
import concurrent.futures
import json
import os
import threading
import time
import requests
import shapely
from common import *

BASE='http://127.0.0.1:18880'
HTTP=[];LOCK=threading.Lock();F=json.loads((P/'fixtures.json').read_text())
def request(method,path,**kwargs):
    s=requests.Session();s.trust_env=False
    r=s.request(method,BASE+path,timeout=45,**kwargs)
    with LOCK:
        HTTP.append({'method':method,'path':path,'params':kwargs.get('params'),'json':kwargs.get('json'),
            'status':r.status_code,'headers':{'content-type':r.headers.get('Content-Type'),'location':r.headers.get('Location')},'body':r.text[:180000]})
        save('pygeoapi-http.json',HTTP)
    return r

def get(collection,params=None):
    r=request('GET','/collections/'+collection+'/items',params={'f':'json',**(params or {})})
    assert r.status_code==200,(r.status_code,r.text[:1000])
    return r.json()

def discovery(e,prefix):
    out={}
    for path in ['/collections/'+prefix+'points','/collections/'+prefix+'points/queryables','/conformance']:
        r=request('GET',path,params={'f':'json'});assert r.status_code==200,r.text[:1000];out[path]=r.json()
    return {'collection_id':out['/collections/'+prefix+'points']['id'],'queryables':'pass','conformance':'pass'}

def fidelity(e,prefix):
    d=get(prefix+'points',{'limit':500});assert len(d['features'])==259,len(d['features'])
    rows={int(x['id']):x for x in d['features']}
    for expected in F['points']:
        actual=rows[expected['id']]
        assert actual['properties']['name']==expected['name']
        assert actual['properties']['attrs']==expected['attrs']
        xy=actual['geometry']['coordinates'];assert abs(xy[0]-expected['x'])<1e-8 and abs(xy[1]-expected['y'])<1e-8,(expected,xy)
    counts={'points':259}
    for table in ['routes','zones','mixed']:
        d=get(prefix+table,{'limit':500});assert len(d['features'])==len(F[table])
        rows={int(x['id']):x for x in d['features']}
        for ident,name,wkt in F[table]:
            assert shapely.geometry.shape(rows[ident]['geometry']).equals(shapely.from_wkt(wkt)),(table,ident,rows[ident]['geometry'])
        counts[table]=len(rows)
    return {'counts':counts,'coordinates':'all match','unicode_quotes_json_null':'all match','geometry_types':'all fixture families'}

def pagination(e,prefix):
    ids=[]
    for offset in range(0,259,25):
        d=get(prefix+'points',{'limit':25,'offset':offset,'sortby':'id'})
        ids.extend(int(x['id']) for x in d['features'])
    assert ids==list(range(1,260)),ids
    return {'pages':11,'unique_ids':259,'duplicates':0}

def attributes(e,prefix):
    d=get(prefix+'points',{'limit':500,'kind':'hospital'});assert len(d['features'])==85
    d=get(prefix+'points',{'limit':500,'filter':"kind='hospital' AND value>=300",'filter-lang':'cql2-text'})
    expected=[x['id'] for x in F['points'] if x['kind']=='hospital' and x['value']>=300]
    assert sorted(int(x['id']) for x in d['features'])==expected
    return {'simple_property_filter':85,'CQL2_scalar_filter':len(expected)}

def bbox(e,prefix):
    d=get(prefix+'points',{'limit':500,'bbox':'116.299,39.799,116.315,39.815'});assert len(d['features'])==64
    d=get(prefix+'routes',{'limit':500,'bbox':'116.307,39.8,116.309,39.83'});assert len(d['features'])==16
    return {'point_bbox':64,'partially_intersecting_routes':16}

def feature(ident,value=777,x=116.314,y=39.814):
    return {'type':'Feature','id':ident,'geometry':{'type':'Point','coordinates':[x,y]},
        'properties':{'name':'E2E 中文 O\'Brien; DROP TABLE points; --','kind':'integration-edit','value':value,'attrs':{'tags':['edit','中文'],'nullable':None}}}

def crud(e,prefix):
    ident=9001;collection=prefix+'points';c=connect(e)
    query(c,'delete from points where id=%s',(ident,));c.close()
    body=feature(ident);r=request('POST','/collections/'+collection+'/items',json=body,headers={'Content-Type':'application/geo+json'})
    assert r.status_code==201,(r.status_code,r.text[:1000])
    r=request('GET',f'/collections/{collection}/items/{ident}',params={'f':'json'});assert r.status_code==200,r.text
    d=r.json();assert d['properties']['name']==body['properties']['name'];assert d['geometry']['coordinates']==body['geometry']['coordinates']
    c=connect(e);v=query(c,'select value,st_srid(geom) from points where id=%s',(ident,));assert norm(v)==[[777,4326]],v;c.close()
    body=feature(ident,888,116.316,39.816);r=request('PUT',f'/collections/{collection}/items/{ident}',json=body,headers={'Content-Type':'application/geo+json'})
    assert r.status_code in (200,204),(r.status_code,r.text[:1000])
    r=request('GET',f'/collections/{collection}/items/{ident}',params={'f':'json'});assert r.json()['properties']['value']==888
    assert r.json()['geometry']['coordinates']==[116.316,39.816],r.text
    r=request('DELETE',f'/collections/{collection}/items/{ident}');assert r.status_code in (200,204),(r.status_code,r.text[:1000])
    c=connect(e);assert not query(c,'select id from points where id=%s',(ident,));assert query(c,'select count(*) from points')[0][0]==259;c.close()
    return {'insert_update_delete':'pass','geometry_and_srid_persisted':'pass','quoted_unicode_properties':'pass'}

def mixed(e,prefix):
    collection=prefix+'points';c=connect(e)
    query(c,'delete from points where id>=9900 and id<=9907');c.close()
    def worker(i):
        ident=9900+i
        for n in range(5):
            body=feature(ident,n,116.31+i*.0001,39.81+n*.0001)
            method='POST' if n==0 else 'PUT';path='/collections/'+collection+'/items'+('' if n==0 else '/'+str(ident))
            r=request(method,path,json=body,headers={'Content-Type':'application/geo+json'});assert r.status_code in (200,201,204),(r.status_code,r.text[:1000])
            d=get(collection,{'limit':500});assert len(d['features'])>=259
            assert all(x['geometry'] and x['geometry']['type']=='Point' for x in d['features'])
        return ident
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:ids=list(ex.map(worker,range(8)))
    c=connect(e)
    for ident in ids:assert query(c,'select value from points where id=%s',(ident,))[0][0]==4
    c.close()
    for ident in ids:
        r=request('DELETE',f'/collections/{collection}/items/{ident}');assert r.status_code in (200,204),r.text
    assert len(get(collection,{'limit':500})['features'])==259
    return {'workers':8,'acknowledged_edits':40,'concurrent_full_collection_reads':40,'final_value_checks':8,'cleanup':'pass'}

for e in os.environ.get('APP_PYGEOAPI_ENGINES','pg,mysql,mo').split(','):
    prefix=e+'-';phase='native'
    for name,fn in [('discovery_queryables',discovery),('read_geometry_properties_all_layers',fidelity),('stable_pagination',pagination),('property_CQL2_filters',attributes),('bbox_point_and_route_intersection',bbox),('CRUD_persisted_geometry',crud)]:
        record('pygeoapi',e,name,lambda e=e,prefix=prefix,fn=fn:fn(e,prefix),phase=phase)
    if e in ['mo','mysql']:
        prefix=e+'-fixed-';phase='adapted'
        for name,fn in [('bbox_point_and_route_intersection',bbox),('CRUD_persisted_geometry',crud),('mixed_8worker_HTTP_edits_reads',mixed)]:
            record('pygeoapi',e,name,lambda e=e,prefix=prefix,fn=fn:fn(e,prefix),phase=phase)
    else:
        record('pygeoapi',e,'mixed_8worker_HTTP_edits_reads',lambda e=e:mixed(e,e+'-'),phase='native')
