"""Functional GIS application workflows with actual database state and independent oracles."""
import concurrent.futures
import csv
import io
import json
import math
from pathlib import Path
import random
import threading
import time

import shapely
from common import P,connect,query,norm,error,equal

RESULTS=[]
LOCK=threading.Lock()


def record(feature,fn,notes=None):
    t=time.monotonic();r={'id':f'APP{len(RESULTS)+1:05d}','feature':feature,'notes':notes}
    try:r['details']=fn();r['status']='pass'
    except Exception as e:r['status']='error';r['error']=error(e)
    r['seconds']=time.monotonic()-t;RESULTS.append(r)
    (P/'application-results.json').write_text(json.dumps(RESULTS,default=str,indent=2))
    print(feature,r['status'],round(r['seconds'],2),str(r.get('error',''))[:200],flush=True)
    return r


def assert_rows(actual,expected,label):
    assert equal(actual,expected,tol=1e-7),(label,norm(actual)[:8],norm(expected)[:8])


def fixture(engines=('mo','pg')):
    pts=[(i*64+j+1,float(i-32),float(j-32)) for i in range(64) for j in range(64)]
    for engine in engines:
        c=connect(engine,180)
        geom='point' if engine=='mo' else 'geometry(Point,0)'
        jtyp='json' if engine=='mo' else 'jsonb'
        for table in ('places','places_scan'):
            query(c,f'create table {table}(id int primary key,label varchar(60),attrs {jtyp},g {geom} not null)')
            sql=f'insert into {table} values(%s,%s,%s,st_geomfromtext(%s,0))'
            vals=[(i,'place_'+str(i),json.dumps({'zone':int(x)//8,'kind':'poi'}),f'POINT({x} {y})') for i,x,y in pts]
            with c.cursor() as q:
                for start in range(0,len(vals),256):q.executemany(sql,vals[start:start+256])
        query(c,'create spatial index places_geo on places(g)' if engine=='mo' else 'create index places_geo on places using gist(g)')
        if engine=='pg':query(c,'analyze places')
        query(c,'create table routes(id int primary key,g geometry)')
        query(c,"insert into routes values(1,st_geomfromtext('LINESTRING(-20 0,0 0,20 0)',0)),(2,st_geomfromtext('LINESTRING(0 -20,0 20)',0)),(3,st_geomfromtext('LINESTRING(25 25,30 30)',0))")
        query(c,'create table zones(id int primary key,g geometry)')
        query(c,"insert into zones values(1,st_geomfromtext('POLYGON((-10 -10,10 -10,10 10,-10 10,-10 -10))',0)),(2,st_geomfromtext('POLYGON((0 0,20 0,20 20,0 20,0 0))',0))")
        query(c,'create table edits(id int primary key,g geometry,v int)')
        query(c,'insert into edits values(1,st_point(1,1),0)')
        c.close()
    (P/'application-fixtures.json').write_text(json.dumps({'points':pts,'zones':2,'routes':3},indent=2))
    return pts


def geofences(pts):
    totals=0
    for engine in ('mo','pg'):
        c=connect(engine)
        for radius in (1,2,5,10,20,30):
            w=f'POLYGON(({-radius} {-radius},{radius} {-radius},{radius} {radius},{-radius} {radius},{-radius} {-radius}))'
            for pred in ('st_contains','st_covers','st_intersects'):
                expected=[(i,) for i,x,y in pts if (abs(x)<radius and abs(y)<radius if pred=='st_contains' else abs(x)<=radius and abs(y)<=radius)]
                for table in ('places','places_scan'):
                    r=query(c,f"select id from {table} where {pred}(st_geomfromtext('{w}',0),g) order by id")
                    assert_rows(r,expected,(engine,pred,radius,table));totals+=1
        c.close()
    return {'queries':totals,'independent_oracle':'grid integer coordinate containment incl boundary policy'}


def nearby(pts):
    checks=0
    for engine in ('mo','pg'):
        c=connect(engine)
        for x,y in ((0,0),(1.25,-2.5),(-30,30),(30,-30)):
            for radius in (0,1,2.5,5,10,50):
                expected=[(i,) for i,a,b in pts if math.hypot(a-x,b-y)<=radius]
                for table in ('places','places_scan'):
                    r=query(c,f'select id from {table} where st_distance(g,st_point({x},{y}))<={radius} order by id')
                    assert_rows(r,expected,(engine,x,y,radius,table));checks+=1
            expected=sorted([(i,math.hypot(a-x,b-y)) for i,a,b in pts],key=lambda r:(round(r[1],12),r[0]))[:25]
            r=query(c,f'select id,d from (select id,st_distance(g,st_point({x},{y})) as d from places) nearest order by cast(d as decimal(30,12)),id limit 25')
            assert_rows(r,expected,(engine,'nearest25'));checks+=1
        c.close()
    return {'queries':checks,'oracle':'Python hypot and deterministic distance/id ordering'}


def spatial_join():
    out={}
    for engine in ('mo','pg'):
        c=connect(engine)
        r=query(c,'select z.id,count(p.id) from zones z join places p on st_contains(z.g,p.g) group by z.id order by z.id')
        assert_rows(r,[(1,361),(2,361)],(engine,'point-in-polygon join'))
        out[engine]=r
        r=query(c,'select r.id,z.id from routes r join zones z on st_intersects(r.g,z.g) order by r.id,z.id')
        assert_rows(r,[(1,1),(1,2),(2,1),(2,2)],(engine,'route-zone join'))
        c.close()
    return out


def overlays():
    out={}
    for engine in ('mo','pg'):
        c=connect(engine)
        q='select st_area(st_union(a.g,b.g)),st_area(st_intersection(a.g,b.g)),st_area(st_difference(a.g,b.g)),st_area(st_symdifference(a.g,b.g)) from zones a,zones b where a.id=1 and b.id=2'
        r=query(c,q);assert_rows(r,[(700.,100.,300.,600.)],(engine,'zoning overlay'));out[engine]=r
        r=query(c,'select id,st_length(g),st_astext(st_lineinterpolatepoint(g,0.5)) from routes where id=1')
        assert_rows(r,[(1,40.,'POINT(0 0)')],(engine,'route interpolation'))
        c.close()
    return out


def exchanges():
    c=connect('mo');p=connect('pg');count=0
    kinds=['POINT(1 2)','LINESTRING(0 0,3 4)','POLYGON((0 0,2 0,2 2,0 2,0 0))',
           'MULTIPOINT((0 0),(1 1))','GEOMETRYCOLLECTION(POINT(1 1),LINESTRING(0 0,2 2))','POINT EMPTY']
    query(c,'create table if not exists exchanged(id int primary key,g geometry)');query(p,'create table if not exists exchanged(id int primary key,g geometry)')
    for i,w in enumerate(kinds,1):
        for src,dst,ss,dd in ((c,p,'mo','pg'),(p,c,'pg','mo')):
            raw=query(src,'select st_asbinary(st_geomfromtext(%s,0))',(w,))[0][0]
            if isinstance(raw,str):raw=bytes.fromhex(raw)
            raw=bytes(raw)
            gx=shapely.from_wkb(raw);assert gx.equals(shapely.from_wkt(w)) or gx.is_empty
            q='insert into exchanged values(%s,st_geomfromwkb(%s,0))'
            query(dst,q,(i,raw));got=query(dst,'select st_astext(g) from exchanged where id=%s',(i,))[0][0]
            assert equal(got,w,mode='geometry'),(ss,dd,w,got);query(dst,'delete from exchanged where id=%s',(i,));count+=1
    # GeoJSON FeatureCollection and CSV materialization: both engines consume
    # the same standard geometry fragments/WKT fields, using their SRID syntax.
    records=query(c,'select id,label,st_asgeojson(g) from places order by id limit 256')
    fc={'type':'FeatureCollection','features':[{'type':'Feature','id':i,'properties':{'label':label},'geometry':json.loads(js)} for i,label,js in records]}
    (P/'features.geojson').write_text(json.dumps(fc))
    for e,db in (('mo',c),('pg',p)):
        query(db,'create table if not exists imported_geojson(id int primary key,g geometry)')
        query(db,'delete from imported_geojson')
        for f in fc['features']:
            js=json.dumps(f['geometry']);ctor='st_geomfromgeojson(%s,0)' if e=='mo' else 'st_setsrid(st_geomfromgeojson(%s),0)'
            query(db,'insert into imported_geojson values(%s,'+ctor+')',(f['id'],js))
        r=query(db,'select id,st_astext(g) from imported_geojson order by id')
        expected=[(f['id'],shapely.to_wkt(shapely.geometry.shape(f['geometry']))) for f in fc['features']]
        assert len(r)==len(expected) and all(a[0]==b[0] and equal(a[1],b[1],mode='geometry') for a,b in zip(r,expected)),(e,'GeoJSON geometry mismatch')
    buf=io.StringIO();w=csv.writer(buf);w.writerow(['id','wkt']);w.writerows(query(c,'select id,st_astext(g) from places order by id limit 256'))
    (P/'features.csv').write_text(buf.getvalue());parsed=list(csv.DictReader(io.StringIO(buf.getvalue())))
    assert len(parsed)==256 and all(shapely.from_wkt(r['wkt']).geom_type=='Point' for r in parsed)
    c.close();p.close();return {'bidirectional_wkb_roundtrips':count,'geojson_import_rows_per_engine':256,'csv_rows':256}


def index_mutation():
    out={}
    for e in ('mo','pg'):
        c=connect(e)
        query(c,'insert into places values(900001,\'edit\',\'{}\',st_point(0.125,0.125))')
        q="select id from places where id>=900000 and st_contains(st_geomfromtext('POLYGON((-1 -1,1 -1,1 1,-1 1,-1 -1))',0),g) order by id"
        assert_rows(query(c,q),[(900001,)],(e,'indexed insert'))
        query(c,'update places set g=st_point(25,25) where id=900001');assert_rows(query(c,q),[],(e,'indexed move outside'))
        query(c,'begin');query(c,'update places set g=st_point(0,0) where id=900001');query(c,'rollback');assert_rows(query(c,q),[],(e,'indexed rollback'))
        query(c,'delete from places where id=900001');assert_rows(query(c,'select count(*) from places'),[(4096,)],(e,'indexed delete'))
        explain=query(c,"explain select id from places where st_contains(st_geomfromtext('POLYGON((-1 -1,1 -1,1 1,-1 1,-1 -1))',0),g)")
        out[e]={'explain':explain};c.close()
    return out


def transactions():
    out={}
    for e in ('mo','pg'):
        a,b=connect(e),connect(e)
        query(a,'begin');query(a,'update edits set g=st_point(2,2),v=1 where id=1')
        assert_rows(query(b,'select st_astext(g),v from edits where id=1'),[('POINT(1 1)',0)],(e,'no dirty reads'))
        query(a,'rollback');assert_rows(query(b,'select st_astext(g),v from edits where id=1'),[('POINT(1 1)',0)],(e,'rollback'))
        query(a,'begin');query(a,'update edits set g=st_point(3,3),v=2 where id=1');query(a,'commit')
        assert_rows(query(b,'select st_astext(g),v from edits where id=1'),[('POINT(3 3)',2)],(e,'committed visibility'))
        query(a,'begin');query(a,'update edits set g=st_point(8,8),v=3 where id=1')
        if e=='mo':
            a._sock.shutdown(2);a._rfile.close();a._sock.close()
        else:a.close()
        deadline=time.monotonic()+15
        while True:
            try:
                query(b,'update edits set v=v+1 where id=1');break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        assert_rows(query(b,'select st_astext(g),v from edits where id=1'),[('POINT(3 3)',3)],(e,'disconnect rollback'))
        out[e]={'dirty_read':False,'rollback':True,'commit':True,'disconnect_rollback':True};b.close()
    return out


def concurrency():
    outcomes={}
    for e in ('mo','pg'):
        c=connect(e);query(c,'create table moving_points(id int primary key,g geometry,v int)')
        for i in range(32):query(c,'insert into moving_points values(%s,st_point(0,0),0)',(i,))
        c.close()
        def worker(i):
            db=connect(e,60)
            for n in range(1,21):
                query(db,'begin');query(db,'update moving_points set g=st_point(%s,%s),v=%s where id=%s',(n,n,n,i));query(db,'commit')
                r=query(db,'select st_x(g),st_y(g),v from moving_points where id=%s',(i,))[0]
                assert r==(n,n,n),(e,i,r)
            db.close();return 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:ack=sum(ex.map(worker,range(32)))
        c=connect(e);r=query(c,'select count(*),sum(v),sum(st_x(g)),sum(st_y(g)) from moving_points');assert_rows(r,[(32,640,640.,640.)],(e,'concurrent final state'));c.close()
        outcomes[e]={'acknowledged_commits':ack,'final_rows':32,'workers':8}
    return outcomes


def postgis_project_features():
    c=connect('pg');out={}
    queries={
     'projection_3857':"select st_x(st_transform(st_setsrid(st_point(1,0),4326),3857))",
     'mapbox_vector_tile':"select octet_length(st_asmvt(t,'poi',4096,'geom')) from (select id,st_asmvtgeom(g,st_makeenvelope(-32,-32,32,32,0),4096,256,true) geom from places limit 100) t",
     'raster_pixels':"select st_value(st_setvalue(st_addband(st_makeemptyraster(2,2,0,0,1,-1,0,0,4326),'8BUI'::text,0,0),1,1,1,7),1,1,1)",
     'topology_create':"select topology.createtopology('gis_app_topology',0)",
     '3d_distance':"select st_3ddistance(st_geomfromtext('POINT Z(0 0 0)'),st_geomfromtext('POINT Z(0 0 3)'))",
     'linear_road_locate':"select st_linelocatepoint(st_geomfromtext('LINESTRING(0 0,10 0)'),st_point(3,0))",
     'cluster_dbscan':"select count(*) from (select st_clusterdbscan(g,eps:=2,minpoints:=2) over () from places limit 100) t",
    }
    for n,s in queries.items():out[n]=query(c,s)
    assert_rows(out['raster_pixels'],[(7.,)],'PostGIS raster');assert_rows(out['3d_distance'],[(3.,)],'PostGIS 3D');assert_rows(out['linear_road_locate'],[(.3,)],'PostGIS road locate')
    assert float(out['projection_3857'][0][0])>111000 and int(out['mapbox_vector_tile'][0][0])>0
    c.close();return out


if __name__=='__main__':
    pts=fixture()
    record('geofence_boundary_and_index_vs_scan',lambda:geofences(pts))
    record('nearby_radius_and_nearest_points',lambda:nearby(pts))
    record('point_polygon_and_route_zone_spatial_joins',spatial_join)
    record('zoning_overlay_and_route_interpolation',overlays)
    record('wkb_geojson_csv_exchange',exchanges)
    record('index_insert_update_delete_and_rollback',index_mutation)
    record('geometry_transaction_visibility_and_disconnect',transactions)
    record('concurrent_geometry_edits',concurrency)
    record('postgis_mapping_raster_topology_3d_projection_projects',postgis_project_features,
           notes='Actual PostGIS-only capabilities, retained separately from shared-engine result comparisons.')
    print('DONE',len(RESULTS),sum(r['status']=='pass' for r in RESULTS),flush=True)
