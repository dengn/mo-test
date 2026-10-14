"""LightRAG 1.5.7 KV/vector prototypes. Graph and document status remain native."""
import asyncio,json,time,math
from dataclasses import dataclass,field
import pymysql
from lightrag.base import BaseKVStorage,BaseVectorStorage

class SQLMixin:
    def _query_sync(self,sql,args=None):
        with pymysql.connect(**self.connection_config) as c:
            with c.cursor() as q:q.execute(sql,args);return q.fetchall()
    async def _query(self,sql,args=None):return await asyncio.to_thread(self._query_sync,sql,args)
    def _batch_sync(self,sql,rows):
        with pymysql.connect(**self.connection_config) as c:
            try:
                c.begin()
                with c.cursor() as q:
                    for row in rows:q.execute(sql,row)
                c.commit()
            except Exception:c.rollback();raise
    async def _batch(self,sql,rows):await asyncio.to_thread(self._batch_sync,sql,rows)
    async def index_done_callback(self):pass  # Namespace batches commit immediately.

@dataclass
class MatrixOneKVStorage(SQLMixin,BaseKVStorage):
    connection_config:dict=field(default_factory=dict)
    supports_strict_point_reads=True
    async def initialize(self):
        await self._query('CREATE TABLE IF NOT EXISTS rag_kv(workspace VARCHAR(128),namespace VARCHAR(128),id VARCHAR(255),payload JSON,PRIMARY KEY(workspace,namespace,id))')
    async def get_by_id(self,id):
        rows=await self._query('SELECT payload FROM rag_kv WHERE workspace=%s AND namespace=%s AND id=%s',(self.workspace,self.namespace,id))
        return json.loads(rows[0][0]) if rows else None
    async def get_by_id_strict(self,id):return await self.get_by_id(id)
    async def get_by_ids(self,ids):return [await self.get_by_id(id) for id in ids]
    async def filter_keys(self,keys):return {key for key in keys if await self.get_by_id(key) is None}
    async def upsert(self,data):
        now=int(time.time());rows=[]
        for id,value in data.items():
            # Decode/encode a copy: framework callers may mutate nested lists.
            payload=json.loads(json.dumps(value));previous=await self.get_by_id(id)
            payload.setdefault('create_time',(previous or {}).get('create_time',now))
            payload.update(update_time=now,_id=id)
            if self.namespace.endswith('text_chunks'):payload.setdefault('llm_cache_list',[])
            rows.append((self.workspace,self.namespace,id,json.dumps(payload,ensure_ascii=False)))
        await self._batch('INSERT INTO rag_kv VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)',rows)
    async def delete(self,ids):
        await self._batch('DELETE FROM rag_kv WHERE workspace=%s AND namespace=%s AND id=%s',[(self.workspace,self.namespace,id) for id in ids])
    async def is_empty(self):
        return (await self._query('SELECT COUNT(*) FROM rag_kv WHERE workspace=%s AND namespace=%s',(self.workspace,self.namespace)))[0][0]==0
    async def drop(self):
        await self._query('DELETE FROM rag_kv WHERE workspace=%s AND namespace=%s',(self.workspace,self.namespace))
        return {'status':'success','message':'namespace data dropped'}

@dataclass
class MatrixOneVectorStorage(SQLMixin,BaseVectorStorage):
    connection_config:dict=field(default_factory=dict)
    def __post_init__(self):
        self._validate_embedding_func();self.dimension=int(self.embedding_func.embedding_dim)
        self.cosine_better_than_threshold=self.global_config.get('vector_db_storage_cls_kwargs',{}).get('cosine_better_than_threshold',.2)
    async def initialize(self):
        await self._query(f'CREATE TABLE IF NOT EXISTS rag_vectors(workspace VARCHAR(128),namespace VARCHAR(128),id VARCHAR(255),payload JSON,embedding VECF32({self.dimension}),PRIMARY KEY(workspace,namespace,id))')
    def _vector(self,value):
        value=[float(v) for v in value]
        if len(value)!=self.dimension or not all(math.isfinite(v) for v in value) or not any(value):raise ValueError('Finite nonzero vector with configured dimension is required')
        return json.dumps(value)
    async def upsert(self,data):
        if not data:return
        ids=list(data);vectors=await self.embedding_func([data[id]['content'] for id in ids]);rows=[]
        if len(vectors)!=len(ids):raise ValueError('Embedding batch length does not match input')
        now=int(time.time())
        for id,vector in zip(ids,vectors):
            payload={k:v for k,v in data[id].items() if k in self.meta_fields};payload['created_at']=now
            rows.append((self.workspace,self.namespace,id,json.dumps(payload,ensure_ascii=False),self._vector(vector)))
        await self._batch('INSERT INTO rag_vectors VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),embedding=VALUES(embedding)',rows)
    async def query(self,query,top_k,query_embedding=None):
        if not isinstance(top_k,int) or top_k<1:raise ValueError('top_k must be a positive integer')
        vector=self._vector(query_embedding if query_embedding is not None else (await self.embedding_func([query]))[0])
        rows=await self._query('SELECT id,payload,1-cosine_distance(embedding,%s) AS score FROM rag_vectors WHERE workspace=%s AND namespace=%s AND 1-cosine_distance(embedding,%s)>%s ORDER BY score DESC,id LIMIT %s',(vector,self.workspace,self.namespace,vector,self.cosine_better_than_threshold,top_k))
        return [dict(json.loads(r[1]),id=r[0],distance=float(r[2])) for r in rows]
    async def get_by_id(self,id):
        rows=await self._query('SELECT payload,embedding FROM rag_vectors WHERE workspace=%s AND namespace=%s AND id=%s',(self.workspace,self.namespace,id))
        return dict(json.loads(rows[0][0]),id=id,vector=json.loads(rows[0][1])) if rows else None
    async def get_by_ids(self,ids):
        results=[await self.get_by_id(id) for id in ids];return [r for r in results if r is not None]
    async def get_vectors_by_ids(self,ids):return {r['id']:r['vector'] for r in await self.get_by_ids(ids)}
    async def delete(self,ids):
        await self._batch('DELETE FROM rag_vectors WHERE workspace=%s AND namespace=%s AND id=%s',[(self.workspace,self.namespace,id) for id in ids])
    async def delete_entity(self,entity_name):raise NotImplementedError('Graph entity deletion is outside this prototype')
    async def delete_entity_relation(self,entity_name):raise NotImplementedError('Graph relation deletion is outside this prototype')
    async def drop(self):
        await self._query('DELETE FROM rag_vectors WHERE workspace=%s AND namespace=%s',(self.workspace,self.namespace))
        return {'status':'success','message':'namespace vectors dropped'}
