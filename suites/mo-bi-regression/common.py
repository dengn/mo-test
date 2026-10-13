"""Portable contracts shared by SQL and native BI regression drivers."""
import csv,datetime,decimal,gzip,hashlib,io,json,math,os,re,time
from pathlib import Path
import pymysql

ROOT=Path(__file__).resolve().parent
D=decimal.Decimal
decimal.getcontext().prec=70
MANIFEST=json.loads((ROOT/'corpus/manifest.json').read_text())

def corpus(name):
    with gzip.open(ROOT/'corpus'/(name+'.jsonl.gz'),'rt',encoding='utf8') as f:
        for line in f:yield json.loads(line)

def scalar(v):
    if v is None or isinstance(v,bool):return v
    if isinstance(v,bytes):return v.decode('utf8')
    if isinstance(v,(datetime.date,datetime.datetime)):v=v.isoformat()
    if isinstance(v,str) and re.fullmatch(r'\d{4}-\d\d-\d\d(?:[ T]\d\d:\d\d:\d\d(?:\.\d+)?Z?)?',v):
        v=datetime.datetime.fromisoformat(v.replace('Z','+00:00'))
        if v.tzinfo:v=v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v.isoformat()
    if isinstance(v,(D,int,float)) and not isinstance(v,bool):
        if isinstance(v,float) and not math.isfinite(v):return str(v)
        n=D(str(v))
        with decimal.localcontext() as ctx:
            ctx.prec=max(70,len(n.as_tuple().digits))
            return '0' if n==0 else format(n.normalize(),'f')
    return v

def canon(rows):return [[scalar(v) for v in row] for row in rows]
def digest(rows):return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def compare(rows,case):
    actual,expected=canon(rows),canon(case['expected'])
    # Numeric strings from JDBC/HTTP must keep exact Decimal value, not float.
    numeric_columns=set()
    width=max((len(row) for row in expected),default=0)
    for ci in range(width):
        values=[row[ci] for row in expected if ci<len(row) and row[ci] is not None]
        if values and all(isinstance(v,str) and re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',v) and scalar(D(v))==v for v in values):numeric_columns.add(ci)
    numeric_columns-=set(case.get('text_columns',[]))
    def numeric_strings(rs):
        out=[]
        for row in rs:
            nr=[]
            for ci,v in enumerate(row):
                if ci in numeric_columns and isinstance(v,str) and re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',v):v=scalar(D(v))
                nr.append(v)
            out.append(nr)
        return out
    actual,expected=numeric_strings(actual),numeric_strings(expected)
    if not case.get('order_check',True):
        key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)
        actual.sort(key=key);expected.sort(key=key)
    if len(actual)!=len(expected):return {'reason':'row_count','expected':len(expected),'actual':len(actual)}
    for ri,(a,e) in enumerate(zip(actual,expected)):
        if len(a)!=len(e):return {'reason':'column_count','row':ri,'expected':len(e),'actual':len(a)}
        for ci,(x,y) in enumerate(zip(a,e)):
            if x==y:continue
            if ci in numeric_columns and x is not None and y is not None:
                try:
                    xd,yd=D(str(x)),D(str(y))
                    if xd==yd:continue
                    policy=case.get('policy','exact')
                    if policy=='analytics' and ci in case.get('approximate_columns',[]) and abs(xd-yd)<=max(D('1e-6'),abs(yd)*D('1e-8')):continue
                    if policy=='ratio' and abs(xd-yd)<=max(D('1e-10'),abs(yd)*D('1e-12')):continue
                    if policy=='avg_integer' and ci==0 and abs(xd-yd)<=D('0.000051'):continue
                except decimal.InvalidOperation:pass
            return {'reason':'cell','row':ri,'column':ci,'expected':y,'actual':x}
    return None

def identifier(v):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',v):raise ValueError('Invalid schema identifier')
    return '`'+v+'`'

def remap(sql,state):
    mapping={'bi_cases20k_20261012':state['schemas']['core'],
             'bi_validation_20261012':state['schemas']['baseline'],
             'bi_other_retest_20261013':state['schemas']['semantic'],
             'bi_extreme_sql_20261012':state['schemas']['extra']}
    pattern=re.compile(r"('(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"|--[^\n]*|/\*[\s\S]*?\*/)|\b("+'|'.join(mapping)+r')\b')
    return pattern.sub(lambda m:m[1] if m[1] is not None else mapping[m[2]],sql)

def connection(database=None,timeout=120):
    if 'MO_PASSWORD' not in os.environ:raise RuntimeError('MO_PASSWORD must be explicitly configured')
    options={'host':os.getenv('MO_HOST','127.0.0.1'),'port':int(os.getenv('MO_PORT','6001')),
             'user':os.getenv('MO_USER','root'),'password':os.environ['MO_PASSWORD'],
             'charset':'utf8mb4','autocommit':True,'connect_timeout':10,
             'read_timeout':timeout,'write_timeout':timeout}
    if database:options['database']=database
    if os.getenv('MO_SSL_CA'):options['ssl']={'ca':os.environ['MO_SSL_CA'],'check_hostname':True}
    return pymysql.connect(**options)

def preflight(expected_commit=None):
    with connection(timeout=15) as cx,cx.cursor() as q:
        q.execute('SELECT VERSION(),git_version(),1');version,commit,one=q.fetchone()
    if 'MatrixOne' not in version or one!=1:raise RuntimeError('Target is not a responsive MatrixOne instance')
    if expected_commit:
        if not re.fullmatch(r'[0-9a-fA-F]{40}',expected_commit):raise ValueError('Expected commit must be a full SHA')
        if not re.fullmatch(r'[0-9a-fA-F]{7,40}',str(commit)) or not expected_commit.lower().startswith(str(commit).lower()):raise RuntimeError('MatrixOne commit mismatch')
    identity=digest([os.getenv('MO_HOST','127.0.0.1'),os.getenv('MO_PORT','6001'),os.getenv('MO_USER','root'),str(commit)])
    return {'version':version,'git_version':commit,'expected_commit':expected_commit,'target_identity':identity}

def safe_error(exc):
    message=str(exc)
    for key in ('MO_PASSWORD','BI_PASSWORD','BI_TOKEN'):
        value=os.getenv(key)
        if value:message=message.replace(value,'[redacted]')
    return {'type':type(exc).__name__,'message':message[:1500]}

def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')

def record(case,rows,**extra):
    diff=compare(rows,case)
    return {'id':case['id'],'status':'mismatch' if diff else 'passed','rows':len(rows),
            'actual_sha256':digest(canon(rows)),**({'difference':diff} if diff else {}),**extra}
