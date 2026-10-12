"""Generate a coverage-first GIS/PostGIS corpus, including independent math oracles."""
import json
import math
from pathlib import Path
import random
import re
import struct

import h3
import s2sphere
import shapely
from common import P,save_cases

SRC=Path('/workspace/matrixone-gis-latest')
CASES=[]
FIXTURES=[
 ('point','POINT(0 0)'),('point2','POINT(3 4)'),('fractional','POINT(1.125 -2.75)'),
 ('line','LINESTRING(0 0,3 4,6 4)'),('closed','LINESTRING(0 0,4 0,4 4,0 4,0 0)'),
 ('polygon','POLYGON((0 0,4 0,4 4,0 4,0 0))'),
 ('hole','POLYGON((0 0,10 0,10 10,0 10,0 0),(2 2,2 4,4 4,4 2,2 2))'),
 ('multipoint','MULTIPOINT((0 0),(3 4),(1 1))'),
 ('multiline','MULTILINESTRING((0 0,3 4),(5 5,8 9))'),
 ('multipolygon','MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)),((4 4,6 4,6 6,4 6,4 4)))'),
 ('collection','GEOMETRYCOLLECTION(POINT(1 1),LINESTRING(0 0,3 4))'),
 ('point_empty','POINT EMPTY'),('line_empty','LINESTRING EMPTY'),
 ('polygon_empty','POLYGON EMPTY'),('multipoint_empty','MULTIPOINT EMPTY'),
 ('multiline_empty','MULTILINESTRING EMPTY'),('multipolygon_empty','MULTIPOLYGON EMPTY'),
 ('collection_empty','GEOMETRYCOLLECTION EMPTY'),
 ('bowtie','POLYGON((0 0,4 4,4 0,0 4,0 0))'),
 ('duplicate','LINESTRING(0 0,0 0,1 0,1 0)'),
 ('spike','POLYGON((0 0,4 0,4 4,2 4,2 5,2 4,0 4,0 0))'),
 ('tiny','POLYGON((0 0,0.000000001 0,0.000000001 0.000000001,0 0.000000001,0 0))'),
 ('large','LINESTRING(1000000000000 1000000000000,1000000000003 1000000000004)'),
 ('negative','POLYGON((-8 -8,-4 -8,-4 -4,-8 -4,-8 -8))'),
 ('null',None),
]
INDEX={n:i+1 for i,(n,w) in enumerate(FIXTURES)}
def lit(s):return "'"+s.replace("'","''")+"'"
def g(w,srid=0):return 'cast(NULL as geometry)' if w is None else f'st_geomfromtext({lit(w)},{srid})'
def add(feature,mo,pg=None,category='functions',mode='scalar',function=None,**kw):
 CASES.append({'id':f'GIS{len(CASES)+1:06d}','category':category,'feature':feature,
               'function':function or feature.split('.')[0], 'mo_sql':mo,
               'pg_sql':mo if pg is None else pg,'mode':mode,**kw})
def call_case(name,ma,pa=None,mode='scalar',variant='constant',**kw):
 pm=name
 mappings={'st_aswkt':'st_astext','st_aswkb':'st_asbinary','st_geomfrombinary':'st_geomfromwkb',
 'st_geometryfromwkb':'st_geomfromwkb','st_linestringfromtext':'st_linefromtext',
 'st_multilinestringfromwkb':'st_mlinefromwkb','st_multipolygonfromwkb':'st_mpolyfromwkb',
 'st_geomcollfromtxt':'st_geomcollfromtext','st_geometrycollectionfromtext':'st_geomcollfromtext',
 'st_geometrycollectionfromwkb':'st_geomcollfromwkb','st_pointatdistance':'st_lineinterpolatepoint',
 'st_distance_sphere':'st_distancesphere'}
 pm=mappings.get(name,name)
 a=f'{name}({ma})';b=f'{pm}({ma if pa is None else pa})'
 if mode=='geometry' and name not in ('st_astext','st_aswkt'):a='st_astext('+a+')';b='st_astext('+b+')'
 if mode=='hex':a='hex('+a+')';b="encode("+b+",'hex')"
 add(name+'.'+variant,'select '+a,'select '+b,mode=mode,function=name,**kw)

def generate():
 text=(SRC/'pkg/sql/plan/function/function_id.go').read_text()
 inventory={n:fid for n,fid in re.findall(r'"((?:st_|mbr|s2_|h3_)[a-z0-9_]+)"\s*:\s*([A-Z0-9_]+)',text)}
 (P/'mo-functions.json').write_text(json.dumps(inventory,indent=2))
 # All native constructors and aliases, plus WKT/WKB I/O on seven types and empties.
 constructors={
 'st_geomfromtext':'point','st_geometryfromtext':'point','st_pointfromtext':'point',
 'st_linefromtext':'line','st_linestringfromtext':'line','st_polyfromtext':'polygon',
 'st_polygonfromtext':'polygon','st_mpointfromtext':'multipoint','st_multipointfromtext':'multipoint',
 'st_mlinefromtext':'multiline','st_multilinestringfromtext':'multiline',
 'st_mpolyfromtext':'multipolygon','st_multipolygonfromtext':'multipolygon',
 'st_geomcollfromtext':'collection','st_geomcollfromtxt':'collection','st_geometrycollectionfromtext':'collection'}
 for name,kind in constructors.items():
  w=FIXTURES[INDEX[kind]-1][1]
  for value in (w,w+' ',None):
   arg='NULL' if value is None else lit(value)
   call_case(name,arg,mode='geometry',variant=str(len(CASES)))
 for name in inventory:
  if name.endswith('fromwkb') or name=='st_geomfrombinary':
   kind=('point' if 'point' in name and 'mpoint' not in name and 'multipoint' not in name else
         'multipoint' if 'mpoint' in name or 'multipoint' in name else
         'multiline' if 'mline' in name or 'multiline' in name else
         'multipolygon' if 'mpoly' in name or 'multipolygon' in name else
         'line' if 'line' in name else 'polygon' if 'poly' in name else
         'collection' if 'coll' in name else 'point')
   w=FIXTURES[INDEX[kind]-1][1];hx=shapely.to_wkb(shapely.from_wkt(w),byte_order=1).hex()
   call_case(name,f'unhex({lit(hx)})',f'decode({lit(hx)},\'hex\')',mode='geometry')
 for name in ('st_astext','st_aswkt','st_aswkb','st_asbinary','st_geometrytype','st_dimension',
              'st_isempty','st_iscollection','st_isvalid','st_issimple','st_numgeometries','st_srid'):
  for kind,w in FIXTURES:
   mode='hex' if name in ('st_aswkb','st_asbinary') else 'typename' if name=='st_geometrytype' else 'geometry' if name in ('st_astext','st_aswkt') else 'scalar'
   # st_astext is already the output conversion.
   expr=f'{name}(g)';pgname='st_asbinary' if name=='st_aswkb' else 'st_astext' if name=='st_aswkt' else name
   pexpr=f'{pgname}(g)'
   if mode=='hex':expr=f'hex({expr})';pexpr=f'encode({pexpr},\'hex\')'
   add(name+'.stored.'+kind,f'select {expr} from geoms where id={INDEX[kind]}',
       f'select {pexpr} from geoms where id={INDEX[kind]}',mode=mode,function=name,
       notes='Stored-column execution, including invalid topology and typed empties.')
   call_case(name,g(w),mode=mode,variant='constant.'+kind)
 unary={
 'st_x':('point2','scalar'),'st_y':('point2','scalar'),
 'st_longitude':('point2','scalar'),'st_latitude':('point2','scalar'),
 'st_swapxy':('line','geometry'),'st_validate':('polygon','geometry'),
 'st_length':('line','scalar'),'st_area':('hole','scalar'),
 'st_startpoint':('line','geometry'),'st_endpoint':('line','geometry'),
 'st_exteriorring':('hole','geometry'),'st_numinteriorrings':('hole','scalar'),
 'st_numinteriorring':('hole','scalar'),'st_numpoints':('line','scalar'),
 'st_isclosed':('closed','scalar'),'st_isring':('closed','scalar'),
 'st_envelope':('hole','geometry'),'st_centroid':('hole','geometry'),
 'st_boundary':('polygon','geometry'),'st_pointonsurface':('polygon','geometry'),
 'st_convexhull':('multipoint','geometry')}
 for name,(kind,mode) in unary.items():
  w=FIXTURES[INDEX[kind]-1][1]
  pg=('st_x' if name=='st_longitude' else 'st_y' if name=='st_latitude' else
      'st_numinteriorrings' if name=='st_numinteriorring' else 'st_force2d' if name=='st_validate' else 'st_flipcoordinates' if name=='st_swapxy' else name)
  for variant,expr in [('constant',g(w)),('null','cast(NULL as geometry)')]:
   mo=f'{name}({expr})';ps=f'{pg}({expr})'
   if mode=='geometry':mo='st_astext('+mo+')';ps='st_astext('+ps+')'
   add(name+'.'+variant,'select '+mo,'select '+ps,mode=mode,function=name,
       notes='PostGIS ST_Force2D is a valid-input control only.' if name=='st_validate' else None)
  mo=f'{name}(g)';ps=f'{pg}(g)'
  if mode=='geometry':mo='st_astext('+mo+')';ps='st_astext('+ps+')'
  add(name+'.stored',f'select {mo} from geoms where id={INDEX[kind]}',f'select {ps} from geoms where id={INDEX[kind]}',mode=mode,function=name)
 # Functions taking extra arguments, not interchangeable overloads.
 extra={
 'st_point':('1,2',None,'geometry'),'st_point32':('1.125,2.25','1.125,2.25','geometry'),
 'st_geometryn':(g(FIXTURES[INDEX['collection']-1][1])+',2',None,'geometry'),
 'st_pointn':(g(FIXTURES[INDEX['line']-1][1])+',2',None,'geometry'),
 'st_interiorringn':(g(FIXTURES[INDEX['hole']-1][1])+',1',None,'geometry'),
 'st_makeenvelope':(g('POINT(0 0)')+','+g('POINT(2 3)'),'0,0,2,3,0','geometry'),
 'st_simplify':(g('LINESTRING(0 0,1 0.01,2 0)')+',0.1',None,'geometry'),
 'st_collect':(g('POINT(0 0)')+','+g('POINT(1 1)'),None,'geometry'),
 'st_lineinterpolatepoint':(g('LINESTRING(0 0,4 0)')+',0.25',None,'geometry'),
 'st_lineinterpolatepoints':(g('LINESTRING(0 0,4 0)')+',0.25',None,'geometry'),
 'st_pointatdistance':(g('LINESTRING(0 0,4 0)')+',1',g('LINESTRING(0 0,4 0)')+',0.25','geometry'),
 'st_frechetdistance':(g('LINESTRING(0 0,4 0)')+','+g('LINESTRING(0 1,4 1)'),None,'scalar'),
 'st_hausdorffdistance':(g('LINESTRING(0 0,4 0)')+','+g('LINESTRING(0 1,4 1)'),None,'scalar'),
 'st_asgeojson':(g('POINT(1 2)'),None,'json'),
 'st_geomfromgeojson':(lit('{"type":"Point","coordinates":[1,2]}'),None,'geometry'),
 'st_geohash':(g('POINT(-5.603 42.605)')+',5',"st_setsrid("+g('POINT(-5.603 42.605)')+",4326),5",'scalar'),
 'st_latfromgeohash':("'ezs42'",None,'scalar'),'st_longfromgeohash':("'ezs42'",None,'scalar'),
 'st_pointfromgeohash':("'ezs42',4326","'ezs42'",'geometry')}
 for name,(ma,pa,mode) in extra.items():
  if name=='st_point32':
   add(name,'select st_astext(st_point32(1.125,2.25))','select st_astext(st_point(1.125,2.25))',mode='geometry',function=name)
  elif name in ('st_latfromgeohash','st_longfromgeohash'):
   pgfn='st_y' if 'latfrom' in name else 'st_x';add(name,'select '+name+"('ezs42')",f"select {pgfn}(st_pointfromgeohash('ezs42'))",function=name)
  else:call_case(name,ma,pa,mode)
 call_case('st_srid',g('POINT(1 2)')+',4326',mode='scalar',variant='setter',comparison='semantic_difference',notes='MO setter overload vs PostGIS getter: tested separately through ST_SetSRID mapping.')
 add('st_srid.setter_mapped','select st_srid(st_srid('+g('POINT(1 2)')+',4326))', 'select st_srid(st_setsrid('+g('POINT(1 2)')+',4326))',function='st_srid',expected=[[4326]])
 # Explicit geometry32 computations: PostGIS has no native float32 type. Inputs
 # are independently rounded before the PG control, rather than pretending it does.
 for name in ('st_x','st_y','st_area','st_length','st_centroid','st_envelope','st_swapxy','st_convexhull'):
  kind='fractional' if name in ('st_x','st_y','st_swapxy') else 'polygon' if name in ('st_area','st_centroid','st_envelope') else 'line' if name=='st_length' else 'multipoint'
  mode='scalar' if name in ('st_x','st_y','st_area','st_length') else 'geometry'
  expr=g(FIXTURES[INDEX[kind]-1][1]);mo=f'{name}(cast({expr} as geometry32))';pg=f'{"st_flipcoordinates" if name=="st_swapxy" else name}({expr})'
  if mode=='geometry':mo=f'st_astext({mo})';pg=f'st_astext({pg})'
  add(name+'.geometry32','select '+mo,'select '+pg,category='float32',mode=mode,function=name,tol=1e-5,notes='Exactly representable float32 fixture; PG uses geometry as independent computation control.')
 # Geodetic controls: PostGIS geometry(4326) computes in degrees, while MO
 # dispatches to spherical math. Cast PG to geography and disable spheroid.
 for lon,lat,dx,dy in [(0,0,1,0),(116.3,39.9,0.01,0),(179,0,2,0),(-179,20,-1,1),(0,80,1,0),(0,-80,0,1)]:
  x2=lon+dx
  if x2>180:x2-=360
  if x2<-180:x2+=360
  a,b=g(f'POINT({lon} {lat})',4326),g(f'POINT({x2} {lat+dy})',4326)
  add('st_distance.geodetic_sphere',f'select st_distance({a},{b})',f'select st_distance(({a})::geography,({b})::geography,false)',category='geodetic',function='st_distance',tol=1e-7)
  add('st_distance.geodetic_spheroid',f'select st_distance({a},{b})',f'select st_distance(({a})::geography,({b})::geography,true)',category='semantics',function='st_distance',comparison='semantic_difference',notes='MO sphere vs PostGIS WGS84 ellipsoid; unequal values are intentional model differences.')
  add('st_distance_sphere',f'select st_distance_sphere({a},{b})',f'select st_distancesphere({a},{b})',category='geodetic',function='st_distance_sphere',tol=1e-7)
 # MatrixOne-specific cell functions validated by independent libraries.
 for lon,lat in [(0,0),(116.3975,39.9087),(-73.9857,40.7484),(179.9,0),(0,89.9)]:
  point=g(f'POINT({lon} {lat})');sid=s2sphere.CellId.from_lat_lng(s2sphere.LatLng.from_degrees(lat,lon))
  for level in (0,5,10,20,30):
   cell=sid.parent(level);sql=f's2_cellid_parent(s2_cellid({point}),{level})'
   add('s2_cellid',f'select {sql}',category='cell_extensions',function='s2_cellid',expect='mo_extension',expected=[[cell.id()]])
   CASES[-1]['pg_sql']=None
   add('s2_cellid_level',f'select s2_cellid_level({sql})',category='cell_extensions',function='s2_cellid_level',expect='mo_extension',expected=[[level]]);CASES[-1]['pg_sql']=None
   for spelling in ('edgeneighbours','edgeneighbors'):
    add('s2_cellid_'+spelling,f'select json_length(s2_cellid_{spelling}({sql}))',category='cell_extensions',function='s2_cellid_'+spelling,expect='mo_extension',expected=[[4]]);CASES[-1]['pg_sql']=None
   for name,args in [('s2_cellid_center',sql),('s2_cellid_area',sql),('s2_cellid_parent',sql+','+str(max(0,level-1))),('s2_cellid_allneighbours',sql),('s2_cellid_allneighbors',sql),('s2_cellid_areneighbours',sql+','+sql),('s2_cellid_areneighbors',sql+','+sql)]:
    add(name,'select '+name+'('+args+')',category='cell_extensions',function=name,expect='mo_extension');CASES[-1]['pg_sql']=None
  for res in (0,3,7,12,15):
   h=h3.latlng_to_cell(lat,lon,res);expr=f'h3_h3index({point},{res})'
   add('h3_h3index','select '+expr,category='cell_extensions',function='h3_h3index',expect='mo_extension',expected=[[int(h,16)]]);CASES[-1]['pg_sql']=None
   for name,args in [('h3_h3index_resolution',expr),('h3_h3index_center',expr),('h3_h3index_boundary',expr),('h3_h3index_parent',expr+','+str(max(0,res-1))),('h3_h3index_neighbours',expr),('h3_h3index_neighbors',expr),('h3_h3index_areneighbours',expr+','+expr),('h3_h3index_areneighbors',expr+','+expr)]:
    add(name,'select '+name+'('+args+')',category='cell_extensions',function=name,expect='mo_extension');CASES[-1]['pg_sql']=None
 # Generated valid geometries with algebraic oracles. No invalid topology is
 # used for differential correctness assertions in this block.
 rng=random.Random(20261012)
 predicates=['st_contains','st_within','st_intersects','st_disjoint','st_touches','st_crosses','st_overlaps','st_equals','st_covers','st_coveredby']
 overlay=['st_union','st_intersection','st_difference','st_symdifference']
 mbr=['mbrcontains','mbrcoveredby','mbrcovers','mbrdisjoint','mbrequals','mbrintersects','mbroverlaps','mbrtouches','mbrwithin']
 for i in range(800):
  x,y=rng.randint(-500,500),rng.randint(-500,500);w,h=rng.randint(1,20),rng.randint(1,20)
  dx,dy=rng.randint(-20,20),rng.randint(-20,20)
  def rect(a,b,c,d):return f'POLYGON(({a} {b},{c} {b},{c} {d},{a} {d},{a} {b}))'
  wa,wb=rect(x,y,x+w,y+h),rect(x+dx,y+dy,x+dx+w,y+dy+h);a,b=g(wa),g(wb)
  ga,gb=shapely.from_wkt(wa),shapely.from_wkt(wb)
  add('st_area.rectangle',f'select st_area({a})',category='generated_geometry',function='st_area',expected=[[w*h]])
  add('st_length.pythagorean',f'select st_length({g(f"LINESTRING({x} {y},{x+3} {y+4})")})',category='generated_geometry',function='st_length',expected=[[5]])
  for name in predicates:
   pyname={'st_equals':'equals','st_coveredby':'covered_by'}.get(name,name.removeprefix('st_'))
   expect=bool(getattr(ga,pyname)(gb))
   add(name+'.rectangle',f'select {name}({a},{b})',category='generated_predicate',function=name,expected=[[expect]])
  if i<200:
   intersection=max(0,min(x+w,x+dx+w)-max(x,x+dx))*max(0,min(y+h,y+dy+h)-max(y,y+dy))
   for name,area in zip(overlay,(2*w*h-intersection,intersection,w*h-intersection,2*w*h-2*intersection)):
    add(name+'.area',f'select st_area({name}({a},{b}))',category='generated_overlay',function=name,expected=[[area]],tol=1e-7)
   for name in mbr:
    pyname={'mbrcoveredby':'covered_by','mbrequals':'equals'}.get(name,name.removeprefix('mbr'))
    # MBR operations compare envelopes; use the mapped exact envelope predicate
    # for PG, not its && bounding-box overlap operator for all relationships.
    pfn='st_'+('coveredby' if pyname=='covered_by' else pyname)
    add(name+'.rectangle',f'select {name}({a},{b})',f'select {pfn}(st_envelope({a}),st_envelope({b}))',category='mbr',function=name,expected=[[bool(getattr(ga,pyname)(gb))]])
  if i<50:
   for name in overlay:call_case(name,a+','+b,mode='geometry',variant='rectangle.'+str(i),category='constructive')
   # Matching polygon approximation resolutions: MO integer segs/quadrant vs
   # PostGIS buffer's quad_segs parameter. Compare area and topology separately.
   point=g(f'POINT({x} {y})')
   add('st_buffer.area',f'select st_area(st_buffer({point},2,8))',f'select st_area(st_buffer({point},2,8))',category='constructive',function='st_buffer',tol=1e-6)
   call_case('st_buffer',point+',2,8',mode='geometry',variant='point.'+str(i),category='constructive',tol=1e-6)
 # Malformed input, arity/subtype/SRID, overflow and nesting boundaries.
 for w in ['','POINT()','POINT(1)','POINT(1 2 3)','POINT Z(1 2 3)','POINT M(1 2 3)','LINESTRING(0 0)','POLYGON((0 0,1 0,1 1))','BOGUS(1 2)','POINT(1e999 0)']:
  add('invalid_wkt',f'select st_geomfromtext({lit(w)})',category='invalid_input',function='st_geomfromtext',expect='mo_gap' if 'POINT Z' in w or 'POINT M' in w or w=='POINT(1 2 3)' else 'reject_both')
 for hx in ['', '00','0101000000','0101000000000000000000','01ffffffff','010300000001000000ffffffff']:
  add('invalid_wkb',f'select st_geomfromwkb(unhex({lit(hx)}))',f"select st_geomfromwkb(decode({lit(hx)},'hex'))",category='invalid_input',function='st_geomfromwkb',expect='reject_both')
 for depth in (1,8,32,63,64,65,128):
  w='POINT(1 2)'
  for _ in range(depth):w='GEOMETRYCOLLECTION('+w+')'
  add('collection_nesting_'+str(depth),'select st_numgeometries('+g(w)+')',category='parser_boundary',function='st_numgeometries',comparison='semantic_difference' if depth>=64 else None,
      notes='MO has a documented parser nesting budget; deeper clean rejection is a capability boundary.')
 for vertices in (10,100,1000,10000,100000):
  w='LINESTRING('+','.join(f'{i} 0' for i in range(vertices))+')'
  add('vertex_boundary_'+str(vertices),'select st_length('+g(w)+')',category='size_boundary',function='st_length',expected=[[vertices-1]],tol=1e-8)
 # PostGIS feature surface sampled using working PostGIS SQL, without treating
 # explicit MO gaps as correctness bugs. Includes native types and project APIs.
 gaps={
 'st_transform':("st_transform("+g('POINT(116.397 39.908)',4326)+",3857)",'geometry'),
 'st_dwithin':(g('POINT(0 0)')+','+g('POINT(1 1)')+',2','scalar'),
 'st_relate':(g('POINT(0 0)')+','+g('POINT(1 1)'),'scalar'),
 'st_makevalid':(g(FIXTURES[INDEX['bowtie']-1][1]),'geometry'),
 'st_subdivide':(g('LINESTRING(0 0,1 0,2 0,3 0,4 0,5 0)')+',5','geometry'),
 'st_snaptogrid':(g('POINT(1.23 4.56)')+',0.1','geometry'),
 'st_segmentize':(g('LINESTRING(0 0,10 0)')+',1','geometry'),
 'st_3ddistance':("st_geomfromtext('POINT Z(0 0 0)'),st_geomfromtext('POINT Z(0 0 1)')",'scalar'),
 'st_astwkb':(g('POINT(1 2)'),'hex'),
 'st_asgml':(g('POINT(1 2)'),'scalar'),
 'st_askml':(g('POINT(1 2)'),'scalar'),
 'st_asencodedpolyline':(g('LINESTRING(0 0,1 1)'),'scalar'),
 'st_clusterdbscan':(g('POINT(1 2)')+',eps:=1,minpoints:=1','scalar')}
 for name,(args,mode) in gaps.items():
  if name=='st_transform':mo=args;pg=args
  elif name=='st_clusterdbscan':mo=name+'('+args+') over ()';pg=mo
  else:mo=name+'('+args+')';pg=mo
  if mode=='geometry':mo='st_astext('+mo+')';pg='st_astext('+pg+')'
  if mode=='hex':mo='hex('+mo+')';pg="encode("+pg+",'hex')"
  add(name+'.feature_probe','select '+mo,'select '+pg,category='postgis_features',function=name,mode=mode,expect='mo_gap')
 covered={c['function'] for c in CASES}
 missing=sorted(set(inventory)-covered)
 (P/'coverage-planned.json').write_text(json.dumps({'registered_names':len(inventory),'canonical_ids':len(set(inventory.values())),
          'covered_names':sorted(set(inventory)&covered),'missing_names':missing,'cases':len(CASES)},indent=2))
 save_cases(CASES)
 (P/'fixtures.json').write_text(json.dumps([{'id':i+1,'name':n,'wkt':w} for i,(n,w) in enumerate(FIXTURES)],indent=2))
 print('generated',len(CASES),'missing',missing)

if __name__=='__main__':generate()
