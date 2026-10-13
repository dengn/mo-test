import json
import os
from pathlib import Path
from qgis.core import QgsApplication,QgsVectorLayer,QgsDataSourceUri,Qgis
from osgeo import gdal

P=Path('/workspace/mo-gis-app-projects')
app=QgsApplication([],False);app.initQgis();out=[]
for e,port,password in [('mysql',63306,''),('mo',6013,'111')]:
    for table in ['points','planar_points']:
        ds=f'MYSQL:gis_app_suite,host=127.0.0.1,port={port},user=root,password={password},tables={table}'
        layer=QgsVectorLayer(ds,e+' '+table,'ogr')
        r={'engine':e,'table':table,'provider':'ogr-mysql','valid':layer.isValid(),'errors':layer.error().summary()}
        if layer.isValid():
            r['feature_count']=layer.featureCount();r['crs']=layer.crs().authid()
            rows=[]
            for i,f in enumerate(layer.getFeatures()):
                rows.append({'id':f['id'],'has_geometry':f.hasGeometry(),'wkt':f.geometry().asWkt()})
                if i==2:break
            r['sample']=rows
        out.append(r)
uri=QgsDataSourceUri();uri.setConnection('127.0.0.1','65432','gis_app_suite','gis','gis_local_test');uri.setDataSource('public','points','geom','','id')
l=QgsVectorLayer(uri.uri(False),'pg points','postgres');r={'engine':'pg','valid':l.isValid(),'feature_count':l.featureCount(),'crs':l.crs().authid()};r['sample']=[{'id':f['id'],'wkt':f.geometry().asWkt()} for f in list(l.getFeatures())[:3]];out.append(r)
(P/'qgis-native-probes.json').write_text(json.dumps({'qgis_version':Qgis.QGIS_VERSION,'results':out},indent=2));print(json.dumps(out,indent=2))
# Destroy providers while the QGIS application/provider registry still lives.
layer=None;l=None;uri=None;f=None
import gc
gc.collect()
app.exitQgis()
