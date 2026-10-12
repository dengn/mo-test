"""Fresh-main GIS bug reproductions plus small application acceptance controls."""
import decimal
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time

import psycopg
import pymysql
import shapely

P = Path(__file__).resolve().parent
COMMIT = '0a4db0e6a6517e489a333ad9073dfcdc5d26aff4'
DB = 'gis_main_verification'

def connect(engine, database=True):
    if engine in ('mo','mysql'):
        return pymysql.connect(host='127.0.0.1',port=6012 if engine=='mo' else 63306,
            user='root',password='111' if engine=='mo' else '',
            database=DB if engine=='mo' and database else None,autocommit=True,
            charset='utf8mb4',connect_timeout=4,read_timeout=30,write_timeout=30)
    return psycopg.connect(host='127.0.0.1',port=65432,user='gis',password='gis_local_test',
        dbname='gis',autocommit=True,connect_timeout=4)

def query(c, sql, args=None):
    with c.cursor() as q:
        q.execute(sql,args)
        return q.fetchall() if q.description else []

def norm(v):
    if isinstance(v,(tuple,list)):
        return [norm(x) for x in v]
    if isinstance(v,(bytes,memoryview)):
        return {'hex':bytes(v).hex()}
    if isinstance(v,decimal.Decimal):
        return str(v)
    if isinstance(v,(datetime.datetime,datetime.date,datetime.time)):
        return v.isoformat()
    return v

def error(e):
    return {'class':type(e).__name__,'code':e.args[0] if e.args else None,
            'sqlstate':getattr(e,'sqlstate',None),'message':str(e)}

A = 'POLYGON((0 0,1 0,1 1,0 1,0 0))'
EDGE = 'POLYGON((1 0,2 0,2 1,1 1,1 0))'
CORNER = 'POLYGON((1 1,2 1,2 2,1 2,1 1))'
LINE = 'LINESTRING(0 0,0 0,1 0,1 0)'
BAD = 'POLYGON((0 0,1 0,1 1))'

def g(wkt):
    return "st_geomfromtext('"+wkt+"',0)"

CASES = [
    ('edge_intersection','MO-GIS-001',f'select st_astext(st_intersection({g(A)},{g(EDGE)}))'),
    ('corner_intersection','MO-GIS-001',f'select st_astext(st_intersection({g(A)},{g(CORNER)}))'),
    ('duplicate_vertex_validity','MO-GIS-002',f'select st_isvalid({g(LINE)})'),
    ('unclosed_ring_wkt','MO-GIS-003',f'select st_astext({g(BAD)})'),
    ('unclosed_ring_geojson','MO-GIS-003',f'select st_asgeojson({g(BAD)})'),
    ('unclosed_ring_wkb','MO-GIS-003',f'select hex(st_aswkb({g(BAD)}))'),
    ('valid_closed_ring_control',None,f'select st_isvalid({g(A)})'),
    ('valid_simple_line_control',None,"select st_isvalid(st_geomfromtext('LINESTRING(0 0,1 0)',0))"),
    ('positive_area_intersection_control',None,f"select st_area(st_intersection({g(A)},st_geomfromtext('POLYGON((0.5 0,1.5 0,1.5 1,0.5 1,0.5 0))',0)))"),
]

def main():
    records=[];versions={'tested_main_commit':COMMIT,'platform':platform.platform(),
        'checked_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'binary_sha256':hashlib.sha256(Path('/workspace/matrixone-gis-latest/mo-service').read_bytes()).hexdigest()}
    c=connect('mo',False)
    v=query(c,'select version(),git_version(),build_version()')
    assert str(v[0][1])==COMMIT[:7],v
    query(c,f'create database if not exists {DB}');c.close()
    for engine in ['mo','pg','mysql']:
        c=connect(engine)
        versions[engine]=norm(query(c,'select version(),git_version(),build_version()' if engine=='mo' else 'select version(),postgis_full_version()' if engine=='pg' else 'select version()'))
        for rep in range(1,4):
            for feature,finding,sql in CASES:
                adapted=sql
                if feature=='unclosed_ring_wkb' and engine=='pg':
                    adapted=f"select encode(st_asbinary({g(BAD)}),'hex')"
                r={'engine':engine,'repeat':rep,'path':'constant','feature':feature,'finding':finding,'sql':adapted}
                try:
                    r['rows']=norm(query(c,adapted))
                    if feature=='unclosed_ring_wkb':
                        try:r['decoded_wkt']=shapely.from_wkb(bytes.fromhex(r['rows'][0][0])).wkt
                        except Exception as e:r['independent_decode_error']=error(e)
                except Exception as e:
                    r['error']=error(e)
                records.append(r)
        c.close()
    c=connect('mo')
    query(c,'drop table if exists repro_geoms')
    query(c,'drop table if exists app_places')
    query(c,'drop table if exists app_planar')
    query(c,'create table repro_geoms(id int primary key,g geometry,h geometry)')
    for i,a,b in [(1,A,EDGE),(2,A,CORNER),(3,LINE,A),(4,BAD,A)]:
        sql='insert into repro_geoms values(%s,st_geomfromtext(%s,0),st_geomfromtext(%s,0))'
        try:
            query(c,sql,(i,a,b));records.append({'engine':'mo','feature':'stored_input_admission','id':i,'rows':[]})
        except Exception as e:
            records.append({'engine':'mo','feature':'stored_input_admission','id':i,'error':error(e)})
    for feature,finding,sql in [
        ('stored_edge_intersection','MO-GIS-001','select st_astext(st_intersection(g,h)) from repro_geoms where id=1'),
        ('stored_corner_intersection','MO-GIS-001','select st_astext(st_intersection(g,h)) from repro_geoms where id=2'),
        ('stored_duplicate_validity','MO-GIS-002','select st_isvalid(g) from repro_geoms where id=3'),
        ('stored_unclosed_geojson','MO-GIS-003','select st_asgeojson(g) from repro_geoms where id=4')]:
        try:r={'engine':'mo','path':'stored','feature':feature,'finding':finding,'sql':sql,'rows':norm(query(c,sql))}
        except Exception as e:r={'engine':'mo','feature':feature,'finding':finding,'sql':sql,'error':error(e)}
        records.append(r)

    (P/'versions.json').write_text(json.dumps(versions,indent=2,ensure_ascii=False)+'\n')
    (P/'recheck-results.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
    # Small application control: explicit geodetic SRID, distance, index and transaction.
    query(c,'create table app_places(id int primary key,label varchar(100),g point not null srid 4326)')
    for i,name,wkt in [(1,'北京','POINT(116.397 39.908)'),(2,'附近点','POINT(116.398 39.909)'),(3,'上海','POINT(121.474 31.230)')]:
        query(c,'insert into app_places values(%s,%s,st_geomfromtext(%s,4326))',(i,name,wkt))
    query(c,'create spatial index app_geo on app_places(g)')
    distance=query(c,'select st_distance(a.g,b.g) from app_places a join app_places b on a.id=1 and b.id=2')[0][0]
    assert 139<float(distance)<142,distance
    inside="select id from app_places where st_contains(st_geomfromtext('POLYGON((116.396 39.907,116.399 39.907,116.399 39.910,116.396 39.910,116.396 39.907))',4326),g) order by id"
    assert norm(query(c,inside))==[[1],[2]]
    plan=query(c,'explain '+inside)
    # The planner deliberately avoids SRID4326 index pushdown until index
    # keys correctly cover antimeridian/geodetic envelopes. Verify this
    # restriction explicitly and test the supported planar path separately.
    assert 'table scan' in str(plan).lower(),plan
    query(c,'create table app_planar(id int primary key,g point not null)')
    for i,x,y in [(1,0,0),(2,1,1),(3,50,50)]:
        query(c,'insert into app_planar values(%s,st_point(%s,%s))',(i,x,y))
    query(c,'create spatial index planar_geo on app_planar(g)')
    planar="select id from app_planar where st_contains(st_geomfromtext('POLYGON((-1 -1,2 -1,2 2,-1 2,-1 -1))',0),g) order by id"
    assert norm(query(c,planar))==[[1],[2]]
    planar_plan=query(c,'explain '+planar)
    assert 'index' in str(planar_plan).lower(),planar_plan
    nearby=query(c,"select id from app_places where st_distance(g,st_geomfromtext('POINT(116.397 39.908)',4326))<=200 order by id")
    assert norm(nearby)==[[1],[2]],nearby
    query(c,'begin');query(c,"update app_places set label='临时' where id=1");query(c,'rollback')
    assert query(c,'select label from app_places where id=1')[0][0]=='北京'
    featurejson=query(c,'select st_asgeojson(g) from app_places order by id')
    assert all(json.loads(r[0])['type']=='Point' for r in featurejson)
    app={'status':'pass','geodetic_distance_m':float(distance),'geofence_ids':[1,2],
         'radius_200m_ids':norm(nearby),'geodetic_explain':norm(plan),
         'geodetic_index_pushdown':'disabled_by_current_planner_correctness_guard',
         'planar_spatial_index_explain':norm(planar_plan),
         'explicit_srid':4326,'rollback':'pass','geojson_points':len(featurejson)}
    c.close()
    (P/'versions.json').write_text(json.dumps(versions,indent=2,ensure_ascii=False)+'\n')
    (P/'recheck-results.json').write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
    (P/'application-acceptance.json').write_text(json.dumps(app,indent=2,ensure_ascii=False)+'\n')
    mo={r['feature']:r for r in records if r['engine']=='mo' and r.get('repeat')==1}
    summary={'mo_main_commit':COMMIT,'records':len(records),'constant_queries':81,'stored_queries':4,
        'confirmed_findings':{
            'MO-GIS-001':mo['edge_intersection'].get('rows')==[['POLYGON EMPTY']] and mo['corner_intersection'].get('rows')==[['POLYGON EMPTY']],
            'MO-GIS-002':mo['duplicate_vertex_validity'].get('rows')==[[0]],
            'MO-GIS-003':bool(mo['unclosed_ring_wkb'].get('independent_decode_error'))},
        'application_acceptance':app['status']}
    (P/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':
    main()
