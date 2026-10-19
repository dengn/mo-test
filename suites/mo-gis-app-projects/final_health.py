"""Verify restored fixtures and real endpoint health after final service changes."""
import json
import re
import requests
from common import *
out={'databases':{},'HTTP':[],'log_scan':{}}
for e in ['mo','pg','mysql']:
    c=connect(e)
    geometry="st_astext(geom,'axis-order=long-lat')" if e=='mysql' else 'st_astext(geom)'
    out['databases'][e]={'counts':{t:query(c,'select count(*) from '+t)[0][0] for t in ['points','routes','zones','mixed']},
        'point1_restored_longitude_latitude':norm(query(c,'select id,value,'+geometry+' from points where id=1'))}
    assert out['databases'][e]['counts']=={'points':259,'routes':16,'zones':4,'mixed':8},out['databases'][e]
    assert out['databases'][e]['point1_restored_longitude_latitude']==[[1,3,'POINT(116.3 39.8)']],out['databases'][e]
    c.close()
s=requests.Session();s.trust_env=False
for u in ['http://127.0.0.1:18880/collections/mo-points/items?f=json&limit=500',
    'http://127.0.0.1:18880/openapi?f=json',
    'http://127.0.0.1:18881'+json.loads((P/'umap-map-identifiers.json').read_text())['view_url'],
    'http://127.0.0.1:18885/','http://127.0.0.1:18883/geoserver/rest/about/version.json']:
    r=s.get(u,timeout=30,auth=('admin','geoserver') if ':18883/'in u else None)
    assert r.status_code==200,(u,r.status_code)
    item={'url':u,'status':r.status_code}
    if '/items?'in u:
        item['features']=len(r.json()['features']);assert item['features']==259
    if '/openapi?'in u:
        item['includes_adapted_collection']='mo-fixed-points'in r.text;assert item['includes_adapted_collection']
    out['HTTP'].append(item)
text=(P/'mo-server.log').read_text()
out['log_scan']={'log_bytes':(P/'mo-server.log').stat().st_size,
    'panic_fatal_race_matches':len(re.findall(r'panic:|fatal error:|DATA RACE',text))}
assert out['log_scan']['panic_fatal_race_matches']==0
save('final-health.json',out);print(json.dumps(out,indent=2))
