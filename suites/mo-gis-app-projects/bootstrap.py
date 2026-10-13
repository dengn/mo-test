"""Prepare separate owned application databases; preserve all earlier GIS data."""
import json
import os
from common import *

pts=[]
for x in range(16):
    for y in range(16):
        ident=x*16+y+1
        pts.append({'id':ident,'name':f'点位 {ident} café O\'Brien','kind':('hospital','school','store')[ident%3],
                    'value':ident*3,'x':116.3+x*.002,'y':39.8+y*.002,'attrs':{'tags':['urban','中文'],'nullable':None,'rank':ident}})
pts += [{'id':257,'name':'上海','kind':'city','value':771,'x':121.474,'y':31.230,'attrs':{'tags':['city']}},
        {'id':258,'name':'New York','kind':'city','value':774,'x':-74.006,'y':40.713,'attrs':{'tags':['city']}},
        {'id':259,'name':'日界线','kind':'city','value':777,'x':179.9,'y':0.1,'attrs':{'tags':['city']}}]
zones=[(1,'西南区','POLYGON((116.299 39.799,116.315 39.799,116.315 39.815,116.299 39.815,116.299 39.799))'),
       (2,'东北区','POLYGON((116.315 39.815,116.331 39.815,116.331 39.831,116.315 39.831,116.315 39.815))'),
       (3,'带洞区','POLYGON((116.299 39.799,116.331 39.799,116.331 39.831,116.299 39.831,116.299 39.799),(116.31 39.81,116.31 39.82,116.32 39.82,116.32 39.81,116.31 39.81))'),
       (4,'跨日界线区','POLYGON((179 -1,-179 -1,-179 1,179 1,179 -1))')]
routes=[(i+1,f'路线 {i+1}',f'LINESTRING(116.3 {39.8+i*.001},116.315 {39.81+i*.001},116.33 {39.8+i*.001})') for i in range(16)]
mixed=[(1,'point','POINT(116.3 39.8)'),(2,'line',routes[0][2]),(3,'polygon',zones[0][2]),(4,'hole',zones[2][2]),
       (5,'multipoint','MULTIPOINT((116.3 39.8),(116.31 39.81))'),
       (6,'multiline','MULTILINESTRING((116.3 39.8,116.31 39.81),(116.32 39.8,116.33 39.81))'),
       (7,'multipolygon','MULTIPOLYGON(((116.3 39.8,116.31 39.8,116.31 39.81,116.3 39.81,116.3 39.8)),((116.32 39.82,116.33 39.82,116.33 39.83,116.32 39.83,116.32 39.82)))'),
       (8,'collection','GEOMETRYCOLLECTION(POINT(116.3 39.8),LINESTRING(116.3 39.8,116.31 39.81))')]
save('fixtures.json',{'points':pts,'zones':zones,'routes':routes,'mixed':mixed})
versions={'mo_commit':MO_COMMIT,'engines':{}}
for e in os.environ.get('APP_BOOTSTRAP_ENGINES','mo,pg,mysql').split(','):
    c=connect(e,db=None)
    if e=='pg':
        for db in [DB,'gis_app_umap']:
            if not query(c,'select 1 from pg_database where datname=%s',(db,)):query(c,'CREATE DATABASE '+db)
    else:
        for db in [DB,'gis_app_umap']:query(c,'create database if not exists '+db)
    c.close();c=connect(e)
    if e=='pg':query(c,'create extension if not exists postgis')
    versions['engines'][e]=norm(query(c,'select version(),git_version(),build_version()' if e=='mo' else 'select version(),postgis_full_version()' if e=='pg' else 'select version()'))
    for table,subtype in [('points','POINT'),('routes','LINESTRING'),('zones','POLYGON'),('mixed','GEOMETRY')]:
        query(c,'drop table if exists '+table)
        typ=f'geometry({subtype if subtype!="GEOMETRY" else "Geometry"},4326)' if e=='pg' else f'{subtype.lower()} not null srid 4326' if e=='mo' else f'{subtype.lower()} not null srid 4326'
        idtyp='serial primary key' if e=='pg' else 'int auto_increment primary key'
        query(c,f'create table {table}(id {idtyp},name varchar(200),kind varchar(40),value int,attrs json,geom {typ})')
    query(c,'drop table if exists planar_points')
    typ='geometry(Point,0)' if e=='pg' else 'point not null'
    idtyp='serial primary key' if e=='pg' else 'int auto_increment primary key'
    query(c,f'create table planar_points(id {idtyp},name varchar(200),kind varchar(40),value int,attrs json,geom {typ})')
    with c.cursor() as q:
        sql='insert into points values(%s,%s,%s,%s,%s,'+geom_constructor(e)+')'
        q.executemany(sql,[(x['id'],x['name'],x['kind'],x['value'],json.dumps(x['attrs'],ensure_ascii=False),f"POINT({x['x']} {x['y']})") for x in pts])
        sql='insert into planar_points values(%s,%s,%s,%s,%s,'+geom_constructor(e,0)+')'
        q.executemany(sql,[(x['id'],x['name'],x['kind'],x['value'],json.dumps(x['attrs'],ensure_ascii=False),f"POINT({x['x']} {x['y']})") for x in pts])
        for table,data in [('zones',zones),('routes',routes),('mixed',mixed)]:
            q.executemany('insert into '+table+' values(%s,%s,%s,%s,%s,'+geom_constructor(e)+')',[(i,n,table,i,json.dumps({'source':'synthetic'}),w) for i,n,w in data])
    for table in ['points','routes','zones','mixed','planar_points']:
        if e=='pg':query(c,f"select setval(pg_get_serial_sequence('{table}','id'),(select max(id) from {table}))")
        query(c,f'create index {table}_geom on {table} using gist(geom)' if e=='pg' else f'create spatial index {table}_geom on {table}(geom)')
    assert query(c,'select count(*) from points')[0][0]==259
    versions['engines'][e]={'versions':versions['engines'][e],'rows':{t:query(c,'select count(*) from '+t)[0][0] for t in ['points','routes','zones','mixed','planar_points']}}
    c.close();print(e,'fixtures ready',flush=True)
save('bootstrap-versions-'+os.environ.get('APP_BOOTSTRAP_ENGINES','all').replace(',','-')+'.json',versions)
