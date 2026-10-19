"""Exercise the real GeoServer REST catalog, WFS/WFS-T and WMS against SQL stores."""
import io
import os
import xml.etree.ElementTree as ET
import requests
from PIL import Image
from common import *

BASE='http://127.0.0.1:18883/geoserver'
S=requests.Session();S.trust_env=False;S.auth=('admin','geoserver')
RESP=[]
PHASE=os.environ.get('APP_GEOSERVER_PHASE','native')

def request(method,path,**kw):
    url=BASE+path;r=S.request(method,url,timeout=90,**kw)
    n=len(RESP)+1;record={'method':method,'path':path,'params':kw.get('params'),'json':kw.get('json'),
        'data':kw.get('data'),'status':r.status_code,'content_type':r.headers.get('Content-Type')}
    if r.headers.get('Content-Type','').startswith('image/'):
        f=f'geoserver-images/response-{n}.png';(P/f).parent.mkdir(exist_ok=True);(P/f).write_bytes(r.content);record['image']=f
    else:record['body']=r.text[:150000]
    RESP.append(record);save('geoserver-http.json',RESP)
    return r

def datastore(engine):
    ws='app_'+engine+('_adapter' if PHASE=='adapted' else '')
    r=request('GET',f'/rest/workspaces/{ws}.json')
    if r.status_code!=200:
        r=request('POST','/rest/workspaces',json={'workspace':{'name':ws}})
        assert r.status_code==201,r.text
    params={'dbtype':'postgis' if engine=='pg' else 'matrixone' if PHASE=='adapted' else 'mysql','host':'127.0.0.1','port':65432 if engine=='pg' else 63306 if engine=='mysql' else MO_PORT,
        'database':DB,'user':'gis' if engine=='pg' else 'root','passwd':'gis_local_test' if engine=='pg' else '' if engine=='mysql' else '111',
        'Expose primary keys':True,'max connections':5,'min connections':1,'Connection timeout':10}
    if engine=='pg':params.update(schema='public',**{'Loose bbox':False})
    r=request('GET',f'/rest/workspaces/{ws}/datastores/sql.json')
    if r.status_code!=200:
        r=request('POST',f'/rest/workspaces/{ws}/datastores',json={'dataStore':{'name':'sql','connectionParameters':{'entry':[{'@key':k,'$':str(v).lower() if isinstance(v,bool) else str(v)} for k,v in params.items()]}}})
        assert r.status_code==201,r.text
    r=request('GET',f'/rest/workspaces/{ws}/datastores/sql/featuretypes.json',params={'list':'available'})
    assert r.status_code==200,r.text
    available=r.text
    configured=request('GET',f'/rest/workspaces/{ws}/datastores/sql/featuretypes.json')
    assert 'points' in available+configured.text,available+configured.text
    return {'workspace':ws,'available':r.json()}

def publish(engine):
    ws='app_'+engine+('_adapter' if PHASE=='adapted' else '');out={}
    for table in ['points','routes','zones']:
        check=request('GET',f'/rest/workspaces/{ws}/datastores/sql/featuretypes/{table}.json')
        if check.status_code==200:
            out[table]='already_published';continue
        r=request('POST',f'/rest/workspaces/{ws}/datastores/sql/featuretypes',json={'featureType':{'name':table,'nativeName':table,
            'title':engine+' '+table,'srs':'EPSG:4326','projectionPolicy':'FORCE_DECLARED',
            'nativeBoundingBox':{'minx':-180,'miny':-2,'maxx':180,'maxy':85,'crs':'EPSG:4326'},
            'latLonBoundingBox':{'minx':-180,'miny':-2,'maxx':180,'maxy':85,'crs':'EPSG:4326'}}})
        assert r.status_code in (201,409),r.text
        out[table]=r.status_code
    return out

def wfs(engine):
    ws='app_'+engine+('_adapter' if PHASE=='adapted' else '');out={}
    for table,count in [('points',259),('routes',16),('zones',4)]:
        r=request('GET','/ows',params={'service':'WFS','version':'2.0.0','request':'GetFeature','typeNames':ws+':'+table,'outputFormat':'application/json','count':500})
        assert r.status_code==200,r.text;d=r.json();assert len(d['features'])==count,(table,len(d['features']))
        out[table]={'count':len(d['features']),'geometry_types':sorted({x['geometry']['type'] for x in d['features']})}
        if table=='points':
            features={int(x['id'].split('.')[-1]):x for x in d['features']};assert set(features)==set(range(1,260))
            assert abs(features[1]['geometry']['coordinates'][0]-116.3)<1e-8,features[1]
            assert abs(features[1]['geometry']['coordinates'][1]-39.8)<1e-8,features[1]
            assert "O'Brien" in features[1]['properties']['name']
    r=request('GET','/ows',params={'service':'WFS','version':'2.0.0','request':'GetFeature','typeNames':ws+':points','outputFormat':'application/json','bbox':'116.299,39.799,116.315,39.815,EPSG:4326','count':500})
    assert r.status_code==200,r.text;d=r.json();out['bbox_count']=len(d['features']);assert out['bbox_count']==64,out
    r=request('GET','/ows',params={'service':'WFS','version':'2.0.0','request':'GetFeature','typeNames':ws+':points','outputFormat':'application/json','cql_filter':"kind='hospital'",'count':500})
    assert r.status_code==200,r.text;d=r.json();assert len(d['features'])==85,d
    out['attribute_filter_count']=len(d['features'])
    return out

def wms(engine):
    ws='app_'+engine+('_adapter' if PHASE=='adapted' else '');r=request('GET','/wms',params={'service':'WMS','version':'1.1.1','request':'GetMap','layers':ws+':points','styles':'',
        'srs':'EPSG:4326','bbox':'116.299,39.799,116.331,39.831','width':640,'height':480,'format':'image/png','transparent':'true'})
    assert r.status_code==200 and r.headers.get('Content-Type','').startswith('image/png'),r.text[:500]
    im=Image.open(io.BytesIO(r.content)).convert('RGBA');assert im.size==(640,480)
    occupied=sum(px[3]>0 for px in im.getdata());assert occupied>100,occupied
    return {'size':im.size,'nontransparent_pixels':occupied}

def transaction(engine):
    ws='app_'+engine+('_adapter' if PHASE=='adapted' else '');ns='http://'+ws
    # Workspace namespace is generated by GeoServer; retrieve it rather than guess.
    r=request('GET',f'/rest/namespaces/{ws}.json');assert r.status_code==200,r.text;ns=r.json()['namespace']['uri']
    point=f'<{ws}:geom><gml:Point srsName="EPSG:4326"><gml:coordinates>116.315,39.815</gml:coordinates></gml:Point></{ws}:geom>'
    base=f'<wfs:Transaction service="WFS" version="1.0.0" xmlns:wfs="http://www.opengis.net/wfs" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:{ws}="{ns}">'
    xml=base+f'<wfs:Insert><{ws}:points><{ws}:name>GIS WFS edit 中文</{ws}:name><{ws}:kind>edit</{ws}:kind><{ws}:value>123</{ws}:value>'+point+f'</{ws}:points></wfs:Insert></wfs:Transaction>'
    r=request('POST','/wfs',data=xml,headers={'Content-Type':'text/xml'});assert r.status_code==200,r.text
    tree=ET.fromstring(r.content);fids=[x.attrib['fid'] for x in tree.iter() if 'fid' in x.attrib];assert len(fids)==1,r.text
    fid=fids[0];ident=int(fid.split('.')[-1]);c=connect(engine)
    assert query(c,'select name,value from points where id=%s',(ident,))[0]==('GIS WFS edit 中文',123)
    xml=base+f'<wfs:Update typeName="{ws}:points"><wfs:Property><wfs:Name>value</wfs:Name><wfs:Value>456</wfs:Value></wfs:Property><ogc:Filter><ogc:FeatureId fid="{fid}"/></ogc:Filter></wfs:Update></wfs:Transaction>'
    r=request('POST','/wfs',data=xml,headers={'Content-Type':'text/xml'});assert r.status_code==200 and 'Exception' not in r.text,r.text
    assert query(c,'select value from points where id=%s',(ident,))[0][0]==456
    xml=base+f'<wfs:Delete typeName="{ws}:points"><ogc:Filter><ogc:FeatureId fid="{fid}"/></ogc:Filter></wfs:Delete></wfs:Transaction>'
    r=request('POST','/wfs',data=xml,headers={'Content-Type':'text/xml'});assert r.status_code==200 and 'Exception' not in r.text,r.text
    assert not query(c,'select id from points where id=%s',(ident,));assert query(c,'select count(*) from points')[0][0]==259;c.close()
    return {'insert_fid':fid,'insert_persisted':True,'update_persisted':True,'delete_persisted':True}

for e in os.environ.get('APP_GEOSERVER_ENGINES','pg,mysql,mo').split(','):
    deploy=record('GeoServer',e,'datastore_discovery',lambda e=e:datastore(e),phase=PHASE)
    if deploy['status']!='pass':continue
    layer=record('GeoServer',e,'publish_points_routes_zones',lambda e=e:publish(e),phase=PHASE)
    if layer['status']!='pass':continue
    record('GeoServer',e,'WFS_features_bbox_attributes',lambda e=e:wfs(e),phase=PHASE)
    record('GeoServer',e,'WMS_png_map_render',lambda e=e:wms(e),phase=PHASE)
    outcome=record('GeoServer',e,'WFS_T_insert_update_delete_persistence',lambda e=e:transaction(e),phase=PHASE)
    if outcome['status']!='pass':
        c=connect(e)
        remaining=query(c,"select id,value,st_astext(geom) from points where name=%s and kind='edit'",('GIS WFS edit 中文',))
        save(f'geoserver-{e}-{PHASE}-failed-write-sideeffects.json',{'rows_after_failed_workflow':remaining,
             'interpretation':'Insert and update were separate requests; failure of a later DELETE does not roll them back.',
             'test_teardown':'Only rows named GIS WFS edit 中文 with kind edit are removed.'})
        query(c,"delete from points where name=%s and kind='edit'",('GIS WFS edit 中文',));c.close()
    save(f'geoserver-{e}-{PHASE}-http.json',RESP)
