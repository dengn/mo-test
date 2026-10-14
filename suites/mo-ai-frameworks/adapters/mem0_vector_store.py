"""Mem0 VectorStoreBase prototype: synchronous dense vectors and scalar equality only."""
import json,re,math
from types import SimpleNamespace
import pymysql
from mem0.vector_stores.base import VectorStoreBase
class Mem0MatrixOne(VectorStoreBase):
    def __init__(self,host,port,user,password,database,collection_name='mem0_vectors',embedding_model_dims=3,**kwargs):
        if kwargs.get('use_azure_credential') or kwargs.get('connection_pool'):raise NotImplementedError('Local SQL connection configuration only')
        self.cfg=dict(host=host,port=port,user=user,password=password,database=database,autocommit=True,connect_timeout=5,read_timeout=20)
        self.collection_name=collection_name;self.dim=embedding_model_dims
        self.create_col(collection_name,self.dim,'cosine')
    def _name(self,name):
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Invalid SQL identifier')
        return name
    def _exec(self,stmt,args=None):
        with pymysql.connect(**self.cfg) as c:
            with c.cursor() as q:q.execute(stmt,args);return q.fetchall()
    def _vector(self,v):
        if len(v)!=self.dim or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v):raise ValueError('Vector must be finite with configured dimension')
        return json.dumps(v)
    def create_col(self,name,vector_size,distance='cosine'):
        if distance not in ('cosine',):raise NotImplementedError('Only cosine metric')
        self._exec(f'CREATE TABLE IF NOT EXISTS {self._name(name)}(id VARCHAR(128) PRIMARY KEY,payload JSON,embedding VECF32({int(vector_size)}))')
    def insert(self,vectors,payloads=None,ids=None):
        if ids is None or payloads is None or not len(vectors)==len(payloads)==len(ids):raise ValueError('Aligned ids/vectors/payloads required')
        c=pymysql.connect(**self.cfg)
        try:
            c.begin()
            with c.cursor() as q:
                for id,v,p in zip(ids,vectors,payloads):q.execute(f'INSERT INTO {self._name(self.collection_name)} VALUES(%s,%s,%s)',(id,json.dumps(p),self._vector(v)))
            c.commit()
        except Exception:c.rollback();raise
        finally:c.close()
    def _where(self,filters):
        parts=[];args=[]
        for key,val in (filters or {}).items():
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',key) or not isinstance(val,(str,int,float,bool)):raise NotImplementedError('Only scalar metadata equality is supported')
            parts.append('JSON_EXTRACT(payload,%s)=CAST(%s AS JSON)');args.extend(['$.'+key,json.dumps(val,ensure_ascii=False,allow_nan=False)])
        return (' WHERE '+' AND '.join(parts) if parts else ''),args
    def search(self,query,vectors,top_k=5,filters=None):
        where,args=self._where(filters);v=self._vector(vectors)
        rows=self._exec(f'SELECT id,payload,cosine_distance(embedding,%s) FROM {self._name(self.collection_name)}'+where+' ORDER BY cosine_distance(embedding,%s),id LIMIT %s',tuple([v]+args+[v,top_k]))
        return [SimpleNamespace(id=r[0],payload=json.loads(r[1]),score=1.-float(r[2])) for r in rows]
    def get(self,vector_id):
        rows=self._exec(f'SELECT id,payload FROM {self._name(self.collection_name)} WHERE id=%s',(vector_id,))
        return SimpleNamespace(id=rows[0][0],payload=json.loads(rows[0][1]),score=None) if rows else None
    def update(self,vector_id,vector=None,payload=None):
        parts=[];args=[]
        if vector is not None:parts.append('embedding=%s');args.append(self._vector(vector))
        if payload is not None:parts.append('payload=%s');args.append(json.dumps(payload))
        if parts:self._exec(f'UPDATE {self._name(self.collection_name)} SET '+','.join(parts)+' WHERE id=%s',tuple(args+[vector_id]))
    def delete(self,vector_id):self._exec(f'DELETE FROM {self._name(self.collection_name)} WHERE id=%s',(vector_id,))
    def list(self,filters=None,top_k=100):
        where,args=self._where(filters)
        rows=self._exec(f'SELECT id,payload FROM {self._name(self.collection_name)}'+where+' ORDER BY id LIMIT %s',tuple(args+[top_k or 100]))
        return [[SimpleNamespace(id=r[0],payload=json.loads(r[1]),score=None) for r in rows]]
    def list_cols(self):return [r[0] for r in self._exec('SHOW TABLES')]
    def delete_col(self):self._exec(f'DROP TABLE IF EXISTS {self._name(self.collection_name)}')
    def col_info(self):return {'name':self.collection_name,'points_count':self._exec(f'SELECT COUNT(*) FROM {self._name(self.collection_name)}')[0][0]}
    def reset(self):self.delete_col();self.create_col(self.collection_name,self.dim,'cosine')
