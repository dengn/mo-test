"""Additional geometry32, geodetic and application-facing overload coverage."""
import json
import re
from pathlib import Path
from common import P,save_cases,run_cases

original=[json.loads(l) for l in (P/'cases.jsonl').read_text().splitlines()]
out=[];done=set()
for c in original:
 name=c['function']
 if name in done or not c.get('mo_sql') or c['category'] not in ('functions','mbr','constructive','generated_predicate','cell_extensions'):continue
 sql=c['mo_sql']
 new=re.sub(r"st_geomfromtext\(('[^']*'),0\)",r'cast(st_geomfromtext(\1,0) as geometry32)',sql)
 if new==sql:continue
 d=dict(c);d.update(id=f'G32{len(out)+1:05d}',mo_sql=new,category='geometry32_surface',feature=c['feature']+'.cast_geometry32',tol=1e-5,notes='MO geometry32 input; PG geometry control uses the same exactly representable fixture. Unsupported overloads are recorded, not hidden by automatic input conversion.')
 out.append(d);done.add(name)
def add(feature,mo,pg,**kw):
 out.append({'id':f'EXTRA{len(out)+1:05d}','category':'additional_surface','feature':feature,'function':feature.split('.')[0],'mo_sql':mo,'pg_sql':pg,**kw})
for x,y,size in ((0,0,1),(116,39,0.01),(0,70,0.1)):
 w=f'POLYGON(({x} {y},{x+size} {y},{x+size} {y+size},{x} {y+size},{x} {y}))'
 m=f"st_geomfromtext('{w}',4326)"
 add('st_area.geography_sphere','select st_area('+m+')','select st_area(('+m+')::geography,false)',tol=1e-7)
 line=f"st_geomfromtext('LINESTRING({x} {y},{x+size} {y+size})',4326)"
 add('st_length.geography_sphere','select st_length('+line+')','select st_length(('+line+')::geography,false)',tol=1e-7)
anti="st_geomfromtext('POLYGON((179 -1,-179 -1,-179 1,179 1,179 -1))',4326)"
for x in (179.5,-179.5,0):
 pt=f"st_geomfromtext('POINT({x} 0)',4326)"
 add('st_covers.antimeridian','select st_covers('+anti+','+pt+')','select st_covers(('+anti+')::geography,('+pt+')::geography)',expected=[[x!=0]])
 add('st_intersects.antimeridian','select st_intersects('+anti+','+pt+')','select st_intersects(('+anti+')::geography,('+pt+')::geography)',expected=[[x!=0]])
for opts in (0,1,2,4,8):
 add('st_asgeojson.options_'+str(opts),f'select st_asgeojson(st_point(1,2),8,{opts})',f'select st_asgeojson(st_point(1,2),8,{opts})',expect='mo_gap')
for feature,mo,pg in [
 ('st_askml.valid_srid',"select st_askml(st_geomfromtext('POINT(1 2)',4326))","select st_askml(st_geomfromtext('POINT(1 2)',4326))"),
 ('st_asencodedpolyline.valid_srid',"select st_asencodedpolyline(st_geomfromtext('LINESTRING(0 0,1 1)',4326))","select st_asencodedpolyline(st_geomfromtext('LINESTRING(0 0,1 1)',4326))"),
 ('st_intersection.line_polygon',"select st_astext(st_intersection(st_geomfromtext('LINESTRING(-1 1,3 1)',0),st_geomfromtext('POLYGON((0 0,2 0,2 2,0 2,0 0))',0)))","select st_astext(st_intersection(st_geomfromtext('LINESTRING(-1 1,3 1)',0),st_geomfromtext('POLYGON((0 0,2 0,2 2,0 2,0 0))',0)))")]:
 add(feature,mo,pg,expect='mo_gap')
save_cases(out,'supplement-cases.jsonl')
run_cases(out,'supplement-results.jsonl',workers=4)
