"""SQL-independent native PyIceberg reproducer for list/UUID null filters."""
import sys,uuid,pathlib,json,traceback,importlib.metadata,collections
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField,LongType,ListType,StringType,UUIDType
from pyiceberg.io.pyarrow import schema_to_pyarrow
from pyiceberg.expressions import IsNull,NotNull
root=pathlib.Path(__file__).resolve().parent/'iceberg-filter-repro';root.mkdir(exist_ok=True)
catalog=load_catalog('native_repro',type='sql',uri='sqlite:///'+str(root/'catalog.db'),warehouse='file://'+str(root/'warehouse'))
ns='repro_'+uuid.uuid4().hex[:8];catalog.create_namespace(ns)
results=[]
for name,typ,values in [('list',ListType(element_id=100,element=StringType(),element_required=False),[None,[],['a'],['a','文']]),('uuid',UUIDType(),[None,uuid.UUID(int=0).bytes,uuid.UUID(int=1).bytes,uuid.UUID(int=2**128-1).bytes])]:
 table=catalog.create_table((ns,name),schema=Schema(NestedField(1,'id',LongType(),required=False),NestedField(2,'v',typ,required=False)))
 table.append(pa.Table.from_pylist([{'id':i,'v':v} for i,v in enumerate(values)],schema=schema_to_pyarrow(table.schema())))
 for scene,expr in [('full_scan',None),('is_null',IsNull('v')),('not_null',NotNull('v'))]:
  r={'type':name,'scene':scene,'identifier':[ns,name],'source':'4 directly constructed native Arrow values; no MatrixOne/MySQL/SQL source'}
  try:
   rows=table.scan(**({'row_filter':expr} if expr is not None else {})).to_arrow().to_pylist()
   expected=[i for i,v in enumerate(values) if expr is None or (v is None if scene=='is_null' else v is not None)]
   actual=sorted(x['id'] for x in rows);assert actual==expected
   r.update(status='passed',ids=actual)
  except Exception as e:r.update(status='execution_failed',error=repr(e),traceback=traceback.format_exc())
  results.append(r)
out={'versions':{n:importlib.metadata.version(n) for n in ['pyiceberg','pyarrow']},'counts':dict(collections.Counter(r['status'] for r in results)),'cases':results,'scope':'Small native local reproduction; independent of MatrixOne; files retained'}
(root/'results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'versions':out['versions'],'counts':out['counts'],'cases':[{k:v for k,v in r.items() if k!='traceback'} for r in results]},ensure_ascii=False))
