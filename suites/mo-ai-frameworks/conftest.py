import os,sys,uuid
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
os.environ.setdefault('MO_RUN_ID',uuid.uuid4().hex[:12])
os.environ.setdefault('MO_REGISTRY',str(ROOT/'results'/os.environ['MO_RUN_ID']/'direct-pytest-databases.json'))
os.environ.setdefault('MO_RUNTIME_DIR',str(ROOT/'results'/os.environ['MO_RUN_ID']/'runtime'))
os.environ['HAYSTACK_TELEMETRY_ENABLED']='false';os.environ['DO_NOT_TRACK']='1'
os.environ['MEM0_TELEMETRY']='False';os.environ['MEM0_DIR']=str(Path(os.environ['MO_RUNTIME_DIR'])/'mem0')
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True';os.environ['DSPY_CACHEDIR']=str(Path(os.environ['MO_RUNTIME_DIR'])/'dspy-cache')
os.environ['HF_HUB_OFFLINE']='1';os.environ['PYDANTIC_AI_NO_BANNER']='1'
from shared import TestDatabase

def pytest_addoption(parser):parser.addoption('--project',default='',help='Comma-separated project ids from projects.json')

def pytest_collection_modifyitems(config,items):
    wanted=set(filter(None,config.getoption('--project').split(',')))
    if not wanted:return
    selected=[];deselected=[];found=set()
    for item in items:
        marker=item.get_closest_marker('project');project=marker.args[0] if marker else None
        if project in wanted:selected.append(item);found.add(project)
        else:deselected.append(item)
    if found!=wanted:raise pytest.UsageError('Projects not present in selected group: '+','.join(sorted(wanted-found)))
    items[:]=selected;config.hook.pytest_deselected(items=deselected)

@pytest.fixture
def db():
    database=TestDatabase()
    try:yield database
    finally:database.drop()

@pytest.fixture
def knowledge(db):
    db.query('CREATE TABLE knowledge(id INT PRIMARY KEY,tenant VARCHAR(128),content TEXT,v VECF32(3))')
    db.query('INSERT INTO knowledge VALUES(%s,%s,%s,%s)',(1,'a','alpha A 中文','[1,0,0]'))
    db.query('INSERT INTO knowledge VALUES(%s,%s,%s,%s)',(2,'b','beta B','[0,1,0]'))
    def lookup(tenant:str,query_text:str)->list[dict]:
        """Retrieve tenant-scoped knowledge from MatrixOne.

        Args:
            tenant: Exact tenant identifier bound as a SQL parameter.
            query_text: Query text mapped to a deterministic test embedding.
        """
        import json
        vector=[1.,0.,0.] if 'alpha' in query_text else [0.,1.,0.]
        rows=db.query('SELECT id,tenant,content FROM knowledge WHERE tenant=%s ORDER BY l2_distance(v,%s) LIMIT 1',(tenant,json.dumps(vector)))
        return [dict(id=r[0],tenant=r[1],content=r[2]) for r in rows]
    return lookup
