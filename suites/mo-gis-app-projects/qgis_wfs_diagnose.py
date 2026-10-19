import gc,json
from pathlib import Path
from qgis.core import QgsApplication,QgsVectorLayer,QgsDataSourceUri,QgsSettings
P=Path('/workspace/mo-gis-app-projects')
app=QgsApplication([],False);app.initQgis()
messages=[]
QgsApplication.messageLog().messageReceived.connect(lambda m,t,l:messages.append({'message':m,'tag':t,'level':int(l)}))
QgsSettings().setValue('cache/directory',str(P/'qgis-cache'))
rows=[]
for version in ['1.0.0','1.1.0','2.0.0']:
 for form in ['uri','encoded']:
  messages.clear();u=QgsDataSourceUri()
  for k,v in {'url':'http://127.0.0.1:18883/geoserver/wfs','typename':'app_pg:points','version':version,'srsname':'EPSG:4326','username':'admin','password':'geoserver','pagingEnabled':'false'}.items():u.setParam(k,v)
  source=u.uri(False) if form=='uri' else bytes(u.encodedUri()).decode()
  layer=QgsVectorLayer(source,'diagnostic','WFS')
  ff=list(layer.getFeatures());r={'version':version,'form':form,'valid':layer.isValid(),'count':layer.featureCount(),'rows':len(ff),'errors':layer.error().summary(),'messages':list(messages),'fields':layer.fields().names()}
  rows.append(r);print(json.dumps(r),flush=True)
  layer=None;ff=None;u=None;gc.collect()
P.joinpath('qgis-wfs-diagnose.json').write_text(json.dumps(rows,indent=2)+'\n')
app.exitQgis()
