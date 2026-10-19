"""Small, explicitly scoped adapters. Exact L2 and tenant equality only; no silent fallbacks."""
import json,re
import pymysql
from langchain_matrixone import MatrixOneVectorStore
from langchain_core.documents import Document

class FilteredMatrixOneVectorStore(MatrixOneVectorStore):
    def similarity_search_by_vector(self,embedding,k=4,**kwargs):
        allowed={'filter'}
        unknown=set(kwargs)-allowed
        if unknown:raise NotImplementedError(f'Unsupported options: {unknown}')
        filt=kwargs.get('filter') or {}
        if not isinstance(filt,dict) or any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',key) for key in filt):
            raise NotImplementedError('Only simple metadata key equality filters are supported')
        if any(not isinstance(v,(str,int,float,bool)) for v in filt.values()):
            raise NotImplementedError('Nested/range/logical filters require implementation')
        for name in [self.table_name,self.content_column,self.metadata_column,self.vector_column]:
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Invalid SQL identifier')
        if self.distance not in ('l2','cosine'):raise NotImplementedError('Only l2 and cosine supported')
        if not isinstance(k,int) or k<1:raise ValueError('k must be positive integer')
        import math
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in embedding):raise ValueError('Invalid vector')
        where=[];params=[]
        for key,val in filt.items():
            where.append(f"JSON_UNQUOTE(JSON_EXTRACT({self.metadata_column}, ?)) = ?")
            params.extend(['$.'+key,str(val).lower() if isinstance(val,bool) else str(val)])
        stmt=f'SELECT {self.content_column}, {self.metadata_column} FROM {self.table_name}'
        if where:stmt+=' WHERE '+' AND '.join(where)
        stmt+=f' ORDER BY {self.distance}_distance({self.vector_column}, ?) LIMIT {k}'
        params.append(json.dumps(embedding));r=self.client.execute(stmt,tuple(params))
        return [Document(page_content=row[0],metadata=json.loads(row[1]) if isinstance(row[1],str) else row[1]) for row in r.rows]

class ExactStore:
    """Common primitive for framework prototypes: explicit ids, tenant column, parameterized DML."""
    def __init__(self,cfg,table,dim=3):
        if not re.fullmatch('[a-zA-Z_][a-zA-Z_0-9]*',table):raise ValueError('Invalid table')
        self.cfg=dict(cfg);self.table=table;self.dim=dim
        self.exec(f'CREATE TABLE IF NOT EXISTS {table}(id VARCHAR(128) PRIMARY KEY,doc_id VARCHAR(128),content TEXT,metadata JSON,tenant VARCHAR(128),embedding VECF32({dim}))')
    def exec(self,stmt,params=None):
        c=pymysql.connect(**self.cfg)
        try:
            with c.cursor() as q:q.execute(stmt,params);return q.fetchall()
        finally:c.close()
    def add(self,id,doc_id,text,metadata,embedding):
        if len(embedding)!=self.dim:raise ValueError('Vector dimension mismatch')
        self.exec(f'INSERT INTO {self.table} VALUES(%s,%s,%s,%s,%s,%s)',(id,doc_id,text,json.dumps(metadata),metadata.get('tenant'),json.dumps(embedding)))
    def search(self,embedding,k=4,tenant=None):
        stmt=f'SELECT id,doc_id,content,metadata,l2_distance(embedding,%s) FROM {self.table}'
        params=[json.dumps(embedding)]
        if tenant is not None:stmt+=' WHERE tenant=%s';params.append(tenant)
        stmt+=' ORDER BY l2_distance(embedding,%s),id LIMIT %s';params.extend([json.dumps(embedding),k])
        return self.exec(stmt,tuple(params))

from llama_index.core.vector_stores.types import BasePydanticVectorStore,VectorStoreQueryResult
from llama_index.core.schema import TextNode
from pydantic import PrivateAttr
class LlamaMatrixOneStore(BasePydanticVectorStore):
    stores_text:bool=True
    _store:ExactStore=PrivateAttr()
    def __init__(self,store):super().__init__();self._store=store
    @property
    def client(self):return self._store
    def add(self,nodes,**kwargs):
        for n in nodes:self._store.add(n.node_id,n.ref_doc_id or n.node_id,n.get_content(),n.metadata,n.get_embedding())
        return [n.node_id for n in nodes]
    def delete(self,ref_doc_id,**kwargs):self._store.exec(f'DELETE FROM {self._store.table} WHERE doc_id=%s',(ref_doc_id,))
    def query(self,query,**kwargs):
        if query.filters is not None:raise NotImplementedError('LlamaIndex filter translation not implemented')
        if query.doc_ids or query.node_ids:
            raise NotImplementedError('Document/node id query filters are not implemented')
        if kwargs or query.alpha is not None or query.output_fields is not None:
            raise NotImplementedError('Additional query options are not implemented')
        if getattr(query.mode,'value',query.mode)!='default':raise NotImplementedError('Only dense vector default mode')
        rows=self._store.search(query.query_embedding,query.similarity_top_k)
        return VectorStoreQueryResult(nodes=[TextNode(id_=r[0],text=r[2],metadata=json.loads(r[3])) for r in rows],ids=[r[0] for r in rows],similarities=[1/(1+float(r[4])) for r in rows])

class HaystackMatrixOneStore:
    def __init__(self,store):self._store=store
    def count_documents(self):return self._store.exec(f'SELECT COUNT(*) FROM {self._store.table}')[0][0]
    def write_documents(self,documents,policy=None):
        from haystack.document_stores.types import DuplicatePolicy
        if policy not in (None,DuplicatePolicy.NONE,DuplicatePolicy.FAIL):raise NotImplementedError('Only fail-on-duplicate writes implemented')
        for d in documents:self._store.add(d.id,d.id,d.content or '',d.meta,d.embedding)
        return len(documents)
    def filter_documents(self,filters=None):
        from haystack import Document
        stmt=f'SELECT id,content,metadata FROM {self._store.table}';params=None
        if filters:
            if set(filters)!={'field','operator','value'}:raise NotImplementedError('Only the complete tenant equality filter is implemented')
            if filters.get('field')!='meta.tenant' or filters.get('operator')!='==':raise NotImplementedError('Only tenant equality filter implemented')
            stmt+=' WHERE tenant=%s';params=(filters['value'],)
        return [Document(id=r[0],content=r[1],meta=json.loads(r[2])) for r in self._store.exec(stmt,params)]
    def delete_documents(self,document_ids):
        for id in document_ids:self._store.exec(f'DELETE FROM {self._store.table} WHERE id=%s',(id,))
    def embedding_retrieval(self,query_embedding,top_k=4,tenant=None):
        from haystack import Document
        return [Document(id=r[0],content=r[2],meta=json.loads(r[3]),score=1/(1+float(r[4]))) for r in self._store.search(query_embedding,top_k,tenant)]
