"""Real QGIS project/render/export/edit workflow using the GeoServer WFS service."""
import json
import gc
import sys
import time
from pathlib import Path
sys.path.insert(0,'/workspace/mo-gis-app-projects/qgis-puredeps')
import pymysql
import psycopg2
from qgis.core import (QgsApplication,Qgis,QgsVectorLayer,QgsDataSourceUri,QgsProject,
    QgsFeatureRequest,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsRectangle,
    QgsMapSettings,QgsMapRendererParallelJob,QgsVectorFileWriter,QgsMarkerSymbol,
    QgsSingleSymbolRenderer,QgsGeometry,QgsPointXY,QgsFeature,QgsSettings)
from qgis.PyQt.QtCore import QSize

P=Path('/workspace/mo-gis-app-projects');OUT=[]
app=QgsApplication([],False);app.initQgis()
QgsSettings().setValue('cache/directory',str(P/'qgis-cache'))
def db(engine):
    if engine=='mo':return pymysql.connect(host='127.0.0.1',port=6013,user='root',password='111',database='gis_app_suite',autocommit=True)
    c=psycopg2.connect(host='127.0.0.1',port=65432,user='gis',password='gis_local_test',dbname='gis_app_suite');c.autocommit=True;return c
def q(c,sql,args=None):
    with c.cursor() as cur:cur.execute(sql,args);return cur.fetchall()

for engine in ['pg','mo']:
    start=time.monotonic();r={'project':'QGIS','engine':engine,'phase':'wfs_native_client','workflow':'project_render_export_geometry_edit'}
    layer=None;local=None;reloaded=None;project=QgsProject.instance()
    try:
        ws='app_pg' if engine=='pg' else 'app_mo_adapter'
        uri=QgsDataSourceUri()
        for k,v in {'url':'http://127.0.0.1:18883/geoserver/wfs','typename':ws+':points','version':'1.1.0','srsname':'EPSG:4326','username':'admin','password':'geoserver','pagingEnabled':'false'}.items():uri.setParam(k,v)
        layer=QgsVectorLayer(uri.uri(False),engine+' GIS points','WFS');assert layer.isValid(),layer.error().summary()
        rows=list(layer.getFeatures());assert len(rows)==259,len(rows);assert all(f.hasGeometry() for f in rows)
        target=next(f for f in rows if int(f['id'])==1);xy=target.geometry().asPoint();assert abs(xy.x()-116.3)<1e-8 and abs(xy.y()-39.8)<1e-8
        symbol=QgsMarkerSymbol.createSimple({'name':'circle','color':'#2266cc','size':'2','outline_color':'#ffffff'})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol));symbol=None
        project.addMapLayer(layer)
        settings=QgsMapSettings();settings.setLayers([layer]);settings.setOutputSize(QSize(800,600))
        crs=QgsCoordinateReferenceSystem('EPSG:3857');settings.setDestinationCrs(crs)
        transform=QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),crs,project)
        settings.setExtent(transform.transformBoundingBox(QgsRectangle(116.299,39.799,116.331,39.831)))
        job=QgsMapRendererParallelJob(settings);job.start();job.waitForFinished();image=job.renderedImage()
        png=P/f'qgis-{engine}-map.png';assert image.save(str(png));assert image.width()==800 and not image.isNull()
        pixels={image.pixel(x,y) for x in range(0,800,5) for y in range(0,600,5)};assert len(pixels)>2,len(pixels)
        filename=P/f'qgis-{engine}-project.qgz';assert project.write(str(filename))
        options=QgsVectorFileWriter.SaveVectorOptions();options.driverName='GPKG';options.layerName='points'
        gpkg=P/f'qgis-{engine}-export.gpkg'
        if gpkg.exists():gpkg.unlink()
        result=QgsVectorFileWriter.writeAsVectorFormatV3(layer,str(gpkg),project.transformContext(),options);assert result[0]==QgsVectorFileWriter.NoError,result
        local=QgsVectorLayer(str(gpkg)+'|layername=points','exported','ogr');assert local.isValid() and local.featureCount()==259
        # Persisted real WFS-T geometry + attribute edit, then restore original row.
        c=db(engine);original=q(c,'select value,st_astext(geom) from points where id=1')[0]
        assert layer.startEditing();assert layer.changeAttributeValue(target.id(),layer.fields().indexOf('value'),12345)
        assert layer.changeGeometry(target.id(),QgsGeometry.fromPointXY(QgsPointXY(116.304,39.804)))
        assert layer.commitChanges(),layer.commitErrors()
        got=q(c,'select value,st_astext(geom) from points where id=1')[0]
        assert got[0]==12345 and '116.304' in got[1] and '39.804' in got[1],got
        assert layer.startEditing();assert layer.changeAttributeValue(target.id(),layer.fields().indexOf('value'),original[0])
        assert layer.changeGeometry(target.id(),QgsGeometry.fromWkt(original[1]));assert layer.commitChanges(),layer.commitErrors()
        final=q(c,'select value,st_astext(geom) from points where id=1')[0];assert final==original,(final,original);c.close();c=None
        r.update(status='pass',details={'qgis_version':Qgis.QGIS_VERSION,'features':259,'all_geometries_present':True,
            'render':png.name,'project':filename.name,'gpkg':gpkg.name,'render_sample_colors':len(pixels),
            'geometry_and_attribute_edit_persisted':True,'restore_persisted':True})
    except Exception as e:
        import traceback
        r.update(status='error',error={'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
    finally:
        r['seconds']=round(time.monotonic()-start,3);OUT.append(r)
        with (P/'workflow-results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
        (P/'qgis-workflow-results.json').write_text(json.dumps(OUT,indent=2,ensure_ascii=False)+'\n');print(json.dumps(r,ensure_ascii=False),flush=True)
        project.removeAllMapLayers()
        target=None;rows=None;layer=None;local=None;reloaded=None;job=None;settings=None;uri=None;transform=None;project=None
        gc.collect()
app.exitQgis()
