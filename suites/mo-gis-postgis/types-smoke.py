#!/usr/bin/env python3
"""Read-only source research companion with isolated GIS DDL/DML smoke checks."""
import json
import math
import os
from pathlib import Path
import time
import pymysql

P = Path(__file__).resolve().parent
OUT = []
DB = os.environ.get('MO_GIS_TEST_DATABASE', 'gis_check_' + str(int(time.time())))
c = pymysql.connect(host='127.0.0.1', port=6011, user='root', password='111',
                    ssl_disabled=True, autocommit=True, read_timeout=60,
                    write_timeout=60, connect_timeout=5)


def run(label, sql, expected=None, reject=None, predicate=None):
    t = time.monotonic()
    r = {'label': label, 'sql': sql}
    try:
        with c.cursor() as q:
            q.execute(sql)
            rows = q.fetchall() if q.description else ()
            r['rows'] = rows
            if reject:
                raise AssertionError('Statement unexpectedly accepted')
            if expected is not None:
                assert rows == expected, (rows, expected)
            if predicate:
                assert predicate(rows), rows
            r['status'] = 'pass'
    except Exception as e:
        r['error'] = {'type': type(e).__name__, 'code': e.args[0] if e.args else None,
                      'message': str(e)[:3000]}
        r['status'] = ('pass_expected_rejection' if reject and
                       not isinstance(e, AssertionError) and
                       reject.lower() in str(e).lower() else 'error')
    r['seconds'] = time.monotonic() - t
    OUT.append(r)
    (P / 'types-results.json').write_text(json.dumps(OUT, indent=2, default=str))
    print(label, r['status'], str(r.get('rows', r.get('error')))[:180], flush=True)
    return r


run('create_database', 'create database ' + DB)
run('use_database', 'use ' + DB)
wkts = {
    'geometry': 'POINT(1 2)',
    'point': 'POINT(1 2)',
    'linestring': 'LINESTRING(0 0,3 4)',
    'polygon': 'POLYGON((0 0,2 0,2 2,0 2,0 0))',
    'multipoint': 'MULTIPOINT((1 2),(3 4))',
    'multilinestring': 'MULTILINESTRING((0 0,3 4),(4 4,5 5))',
    'multipolygon': 'MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)))',
    'geometrycollection': 'GEOMETRYCOLLECTION(POINT(1 2),LINESTRING(0 0,3 4))',
    'geography': 'POINT(1 2)',
}
for is32 in (False, True):
    for kind, wkt in wkts.items():
        typ = kind + ('32' if is32 else '')
        tname = 't_' + typ
        srid = 4326 if kind == 'geography' else 0
        run(typ + '_ddl', f'create table {tname}(id int primary key,g {typ})')
        run(typ + '_insert', f"insert into {tname} values(1,st_geomfromtext('{wkt}',{srid}))")
        actual_kind = wkt.split('(')[0].upper()
        run(typ + '_read', f'select st_geometrytype(g),st_srid(g),st_astext(g) from {tname}',
            predicate=lambda rows, ak=actual_kind, sr=srid:
                len(rows) == 1 and rows[0][0] == ak and int(rows[0][1]) == sr and bool(rows[0][2]))
        run(typ + '_show', f'show create table {tname}')

for i, definition in enumerate(("geometry('point',4326)",
                                 "geometry(type='point',srid=4326)",
                                 'point srid 4326')):
    name = f'argument_form_{i}'
    create = run(name + '_ddl', f'create table {name}(g {definition})',
                 reject='syntax' if i < 2 else None)
    if create['status'] == 'pass':
        run(name + '_insert', f"insert into {name} values(st_geomfromtext('POINT(1 2)',4326))")
        run(name + '_read', f'select st_srid(g),st_x(g),st_y(g) from {name}',
            expected=((4326, 1.0, 2.0),))

run('stored_wkb_widths', 'select length(cast(a.g as varbinary)),length(cast(b.g as varbinary)),length(st_asbinary(b.g)) from t_point a,t_point32 b',
    expected=((21, 13, 21),))
run('cartesian_distance', "select st_distance(st_point(0,0),st_point(3,4))", expected=((5.0,),))
run('cartesian_area_length', "select st_area(st_geomfromtext('POLYGON((0 0,2 0,2 2,0 2,0 0))')),st_length(st_geomfromtext('LINESTRING(0 0,3 4)'))", expected=((4.0, 5.0),))
run('geodetic_distance_meters', "select st_distance(st_geomfromtext('POINT(0 0)',4326),st_geomfromtext('POINT(1 0)',4326))",
    predicate=lambda r: len(r)==1 and 111000 < float(r[0][0]) < 111400)
run('contains', "select st_contains(st_geomfromtext('POLYGON((0 0,2 0,2 2,0 2,0 0))'),st_point(1,1))", expected=((True,),))
run('geojson_io', "select st_astext(st_geomfromgeojson('{\"type\":\"Point\",\"coordinates\":[1,2]}')),st_asgeojson(st_point(1,2))",
    predicate=lambda r: r[0][0]=='POINT(1 2)' and json.loads(r[0][1])['coordinates']==[1,2])
run('wkb_roundtrip', 'select st_astext(st_geomfromwkb(st_asbinary(g))) from t_point', expected=(('POINT(1 2)',),))
run('subtype_rejection', "insert into t_point values(2,st_geomfromtext('LINESTRING(0 0,1 1)'))", reject='cannot store')
run('subtype_rejection_atomicity', 'select count(*) from t_point', expected=((1,),))
run('srid_mismatch', "insert into argument_form_2 values(st_geomfromtext('POINT(1 2)',0))", reject='srid')
run('unsupported_srid_ddl', 'create table other_srid(g geometry srid 3857)')
run('unsupported_srid_measure', "select st_distance(st_geomfromtext('POINT(0 0)',3857),st_geomfromtext('POINT(1 0)',3857))", reject='srid')
run('z_coordinates', "select st_geomfromtext('POINT Z (1 2 3)')", reject='invalid geometry type')
run('projection_transform', 'select st_transform(g,3857) from t_point', reject='st_transform')
run('geometry_primary_key', 'create table bad_geo_pk(g geometry primary key)', reject='primary key')
run('geometry_unique_index', 'create unique index bad_geo_unique on t_point(g)', reject='unique')

run('spatial_ddl', 'create table indexed_pts(id int primary key,g point not null)')
run('spatial_create_index', 'create spatial index geo_idx on indexed_pts(g)')
run('spatial_insert', "insert into indexed_pts values(1,st_point(1,1)),(2,st_point(8,8)),(3,st_point(0.5,0.5))")
run('spatial_show', 'show create table indexed_pts')
poly = "st_geomfromtext('POLYGON((0 0,2 0,2 2,0 2,0 0))')"
query = f'select id from indexed_pts where st_contains({poly},g) order by id'
run('spatial_query', query, expected=((1,), (3,)))
run('spatial_explain', 'explain ' + query)
run('spatial_update', 'update indexed_pts set g=st_point(1.5,1.5) where id=2')
run('spatial_after_update', query, expected=((1,), (2,), (3,)))
run('spatial_delete', 'delete from indexed_pts where id=1')
run('spatial_after_delete', query, expected=((2,), (3,)))
run('health', 'select 1', expected=((1,),))
c.close()
summary = {'statements': len(OUT), 'pass': sum(r['status']=='pass' for r in OUT),
           'expected_rejections': sum(r['status']=='pass_expected_rejection' for r in OUT),
           'errors': [{'label':r['label'],'error':r.get('error')} for r in OUT if r['status']=='error'],
           'tested_binary_commit':'f1fc3f944e0835af83115675ea18c950be2c2937',
           'latest_main_observed':'f1fc3f944e0835af83115675ea18c950be2c2937'}
summary['database'] = DB
(P/'types-summary.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary), flush=True)
