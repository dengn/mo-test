import importlib.metadata
import json
import os
from pathlib import Path
import time
from common import connect,query,P,DB,MO_PORT,norm

fixtures=json.loads((P/'fixtures.json').read_text())
versions=json.loads((P/'versions.json').read_text()) if (P/'versions.json').exists() else {}
for engine in os.environ.get('GIS_BOOTSTRAP_ENGINES','mo,pg').split(','):
 c=connect(engine,120,database=False)
 if engine=='mo':
  query(c,f'create database if not exists {DB}');query(c,f'use {DB}')
  versions[engine]={'version':query(c,'select version(),git_version(),build_version()'), 'port':MO_PORT,
                    'isolation':query(c,'select @@transaction_isolation')}
 else:
  query(c,'create extension if not exists postgis');query(c,'create extension if not exists postgis_raster');query(c,'create extension if not exists postgis_topology');query(c,'create schema if not exists gis_suite');query(c,'set search_path=gis_suite,public')
  versions[engine]={'version':query(c,'select version(),postgis_full_version()'),
                    'isolation':query(c,'show transaction_isolation')}
 query(c,'create table geoms(id int primary key,kind varchar(50),g geometry)')
 for f in fixtures:
  if f['wkt'] is None:query(c,'insert into geoms values(%s,%s,NULL)',(f['id'],f['name']))
  else:query(c,'insert into geoms values(%s,%s,st_geomfromtext(%s,0))',(f['id'],f['name'],f['wkt']))
 c.close()
versions['mo_commit']='f1fc3f944e0835af83115675ea18c950be2c2937'
versions['python']={x:importlib.metadata.version(x) for x in ('PyMySQL','psycopg','shapely','pyproj','h3','s2sphere')}
(P/'versions.json').write_text(json.dumps(versions,default=str,indent=2))
print(json.dumps(versions,default=str),flush=True)
