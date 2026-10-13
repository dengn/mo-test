"""Isolate the GDAL MySQL consumer and compare native geometry wire values."""
import json
import sys
from pathlib import Path
from osgeo import ogr,gdal
sys.path.insert(0,'/workspace/mo-gis-app-projects/qgis-puredeps')
import pymysql

P=Path('/workspace/mo-gis-app-projects');out=[]
for e,port,password in [('mysql',63306,''),('mo',6013,'111')]:
    c=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,database='gis_app_suite')
    with c.cursor() as q:
        q.execute('select geom,st_aswkb(geom),st_srid(geom) from planar_points where id=1');v=q.fetchone()
        raw=v[0].encode() if isinstance(v[0],str) else v[0]
        r={'engine':e,'raw_type_code':q.description[0][1],'raw_python_type':type(v[0]).__name__,
           'raw_hex':raw.hex(),'raw_bytes':len(raw),'explicit_wkb_hex':v[1].hex(),
           'explicit_srid':v[2],'mysql_geometry_binary_prefix_valid':len(raw)>4 and raw[4] in (0,1)}
    c.close()
    messages=[]
    def handle(cls,number,message):messages.append({'class':cls,'number':number,'message':message})
    gdal.PushErrorHandler(handle)
    ds=ogr.Open(f'MYSQL:gis_app_suite,host=127.0.0.1,port={port},user=root,password={password},tables=planar_points')
    r['gdal_open']=bool(ds)
    if ds:
        layer=ds.GetLayerByName('planar_points');rows=[]
        for i in range(3):
            feature=layer.GetNextFeature()
            if not feature:break
            geom=feature.GetGeometryRef();idx=feature.GetFieldIndex('id')
            rows.append({'id':feature.GetField('id') if idx>=0 else feature.GetFID(),'wkt':geom.ExportToWkt() if geom else None})
            geom=None;feature=None
        r['gdal_sample']=rows;layer=None;ds=None
    gdal.PopErrorHandler();r['gdal_errors']=messages;out.append(r)
(P/'gdal-wire-probe.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
