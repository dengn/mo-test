import os
import pathlib
import yaml
from common import P,DB,MO_PORT,save

base=yaml.safe_load((P/'projects/pygeoapi/pygeoapi-config.yml').read_text())
base['server'].update(bind={'host':'127.0.0.1','port':18880},url='http://127.0.0.1:18880',cors=True)
base['server']['limits']={'default_items':20,'max_items':500}
base['server']['map']={'url':'http://127.0.0.1:18880/static/local-tile.png','attribution':'Synthetic test features; no external basemap'}
base['metadata']['identification']['title']={'en':'MO GIS open-source application verification'}
base['resources']={}
for engine in ['pg','mysql','mo']:
    for table in ['points','routes','zones','mixed','planar_points']:
        key=engine+'-'+table
        data={'host':'127.0.0.1','port':65432 if engine=='pg' else 63306 if engine=='mysql' else MO_PORT,
              'dbname':DB,'user':'gis' if engine=='pg' else 'root',
              'password':'gis_local_test' if engine=='pg' else '' if engine=='mysql' else '111',
              'search_path':['public' if engine=='pg' else DB]}
        base['resources'][key]={'type':'collection','title':key,'description':'Actual SQL-backed synthetic GIS application dataset',
            'keywords':['gis','integration'],'extents':{'spatial':{'bbox':[-180,-2,180,85],'crs':'http://www.opengis.net/def/crs/OGC/1.3/CRS84'}},
            'providers':[{'type':'feature','name':'PostgreSQL' if engine=='pg' else 'MySQL',
                'data':data,'table':table,'id_field':'id','geom_field':'geom','editable':True,
                'storage_crs':'http://www.opengis.net/def/crs/EPSG/0/4326'}]}
cfg=P/'pygeoapi-native.yml';cfg.write_text(yaml.safe_dump(base,allow_unicode=True,sort_keys=False))
print(cfg)
