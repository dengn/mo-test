"""Real GeoDjango CRUD and spatial lookup against each native backend."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

import pymysql
pymysql.install_as_MySQLdb()
from django.conf import settings
settings.configure(
 SECRET_KEY='synthetic-local-gis-test',INSTALLED_APPS=['django.contrib.contenttypes','django.contrib.gis'],
 DATABASES={
  'default':{'ENGINE':'django.contrib.gis.db.backends.postgis','HOST':'127.0.0.1','PORT':'65432','NAME':'gis','USER':'gis','PASSWORD':'gis_local_test'},
  'mo':{'ENGINE':'django.contrib.gis.db.backends.mysql','HOST':'127.0.0.1','PORT':'6011','NAME':'gis_functional_20261012','USER':'root','PASSWORD':'111','OPTIONS':{'ssl_disabled':True}},
 },USE_TZ=True,DEFAULT_AUTO_FIELD='django.db.models.AutoField')
import django
django.setup()
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point,Polygon
from django.contrib.gis.db.models.functions import Distance,AsGeoJSON
from django.db import connections
from django.db.models.expressions import RawSQL

class ExplicitSRIDPointField(models.PointField):
 def db_type(self,connection):
  if connection.vendor=='mysql':return 'point srid 4326'
  return super().db_type(connection)
 def get_placeholder(self,value,compiler,connection):
  if connection.vendor=='mysql':return 'ST_GeomFromText(%s,4326)'
  return super().get_placeholder(value,compiler,connection)

class Place(models.Model):
 name=models.CharField(max_length=60)
 location=(ExplicitSRIDPointField if os.environ.get('GEO_DJANGO_ADAPTED')=='3' else models.PointField)(srid=4326)
 class Meta:app_label='gis_probe';db_table='geodjango_places_'+django.get_version().replace('.','_')+('_mapped'+os.environ['GEO_DJANGO_ADAPTED'] if os.environ.get('GEO_DJANGO_ADAPTED') else '')+os.environ.get('GEO_DJANGO_TABLE_SUFFIX','')

P=Path(__file__).resolve().parent
RESULT_FILE=os.environ.get('GEO_DJANGO_RESULTS','geodjango-results.json')
out=[]
for alias in os.environ.get('GEO_DJANGO_ENGINES','default,mo').split(','):
 r={'backend':alias,'django_version':django.get_version()};t=time.monotonic()
 r['adapted']=bool(os.environ.get('GEO_DJANGO_ADAPTED'))
 try:
  with connections[alias].schema_editor() as ed:ed.create_model(Place)
  if alias=='mo' and os.environ.get('GEO_DJANGO_ADAPTED')=='3':
   with connections[alias].cursor() as cursor:
    cursor.execute('create spatial index gd_geo on '+Place._meta.db_table+'(location)')
  if alias=='mo' and os.environ.get('GEO_DJANGO_ADAPTED')=='2':
   with connections[alias].cursor() as cursor:
    cursor.execute('alter table '+Place._meta.db_table+' modify column location point srid 4326 not null')
  Place.objects.using(alias).bulk_create([
   Place(name='beijing',location=Point(116.397,39.908,srid=4326)),
   Place(name='shanghai',location=Point(121.474,31.230,srid=4326)),
   Place(name='nearby',location=Point(116.398,39.909,srid=4326))])
  assert Place.objects.using(alias).count()==3
  first=Place.objects.using(alias).get(name='beijing');assert first.location.srid==4326 and abs(first.location.x-116.397)<1e-8
  fence=Polygon(((116,39),(117,39),(117,41),(116,41),(116,39)),srid=4326)
  if alias=='mo' and os.environ.get('GEO_DJANGO_ADAPTED')=='3':
   inside=RawSQL('ST_Within(location,ST_GeomFromText(%s,4326))',[fence.wkt],output_field=models.BooleanField())
   q=Place.objects.using(alias).alias(_inside=inside).filter(_inside=True).order_by('name')
  else:q=Place.objects.using(alias).filter(location__within=fence).order_by('name')
  names=list(q.values_list('name',flat=True));assert names==['beijing','nearby'],names
  distance_expr=RawSQL('ST_Distance(location,ST_GeomFromText(%s,4326))',['POINT(116.397 39.908)'],output_field=models.FloatField()) if alias=='mo' and os.environ.get('GEO_DJANGO_ADAPTED')=='3' else Distance('location',Point(116.397,39.908,srid=4326))
  q=Place.objects.using(alias).annotate(distance=distance_expr).order_by('distance','name')
  distances=[(a.name,str(a.distance)) for a in q];assert [n for n,d in distances]==['beijing','nearby','shanghai'],distances
  r['distance_values']=distances
  if os.environ.get('GEO_DJANGO_ADAPTED') in ('2','3'):
   near=list(q)[1].distance
   meters=near.m if hasattr(near,'m') else float(near)
   assert 139 < meters < 142,('distance unit mismatch',meters)
   r['distance_unit_oracle']='meters: local ~140m pair'
  # MO's registered ST_AsGeoJSON lacks the third options parameter used by
  # native GeoDjango. Keep the native failure record; this is an explicit app
  # adaptation, not a claim of transparent compatibility.
  expr=models.Func(models.F('location'),models.Value(8),function='ST_AsGeoJSON',output_field=models.TextField()) if os.environ.get('GEO_DJANGO_ADAPTED') else AsGeoJSON('location')
  jsonrows=list(Place.objects.using(alias).annotate(js=expr).values_list('js',flat=True));assert len(jsonrows)==3 and all(json.loads(x)['type']=='Point' for x in jsonrows)
  first.location=Point(116.5,40,srid=4326);first.save(using=alias,update_fields=['location'])
  assert abs(Place.objects.using(alias).get(name='beijing').location.y-40)<1e-8
  Place.objects.using(alias).filter(name='shanghai').delete();assert Place.objects.using(alias).count()==2
  r.update(status='pass',within_names=names,distances=distances,checks=['schema+native spatial index','bulk insert','geometry object read','within lookup','distance annotation','GeoJSON annotation','update','delete'])
 except Exception as e:r.update(status='error',error=str(e),traceback=traceback.format_exc())
 r['seconds']=time.monotonic()-t;out.append(r);(P/RESULT_FILE).write_text(json.dumps(out,indent=2));print(json.dumps(r),flush=True)
