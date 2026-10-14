import json,uuid
from contextlib import contextmanager
import pytest

@contextmanager
def memory_factories():
    from mem0.utils.factory import VectorStoreFactory,EmbedderFactory,LlmFactory
    from mem0.configs.llms.base import BaseLlmConfig
    saved=(VectorStoreFactory.provider_to_class['azure_mysql'],EmbedderFactory.provider_to_class['openai'],LlmFactory.provider_to_class['openai'])
    try:
        VectorStoreFactory.provider_to_class['azure_mysql']='adapters.mem0_vector_store.Mem0MatrixOne'
        EmbedderFactory.provider_to_class['openai']='adapters.mem0_test_providers.FixtureEmbedding'
        LlmFactory.provider_to_class['openai']=('adapters.mem0_test_providers.NoCallLLM',BaseLlmConfig)
        yield
    finally:VectorStoreFactory.provider_to_class['azure_mysql'],EmbedderFactory.provider_to_class['openai'],LlmFactory.provider_to_class['openai']=saved

def new_memory(db,tmp_path):
    from mem0 import Memory
    from mem0.configs.base import MemoryConfig
    config=MemoryConfig.model_validate({'vector_store':{'provider':'azure_mysql','config':dict(db.sdk_config,collection_name='memories',embedding_model_dims=3)},'embedder':{'provider':'openai','config':{'embedding_dims':3}},'llm':{'provider':'openai','config':{}},'history_db_path':str(tmp_path/'history.sqlite')})
    with memory_factories():return Memory(config)

def vector_store(db,name):
    from adapters.mem0_vector_store import Mem0MatrixOne
    return Mem0MatrixOne(**db.sdk_config,collection_name=name,embedding_model_dims=3)

@pytest.mark.project('mem0')
def test_mem0_memory_lifecycle_filter_reopen(db,tmp_path):
    first=reopened=None
    try:
        first=new_memory(db,tmp_path)
        aid=first.add('alpha memory A',user_id='a',infer=False)['results'][0]['id']
        bid=first.add('beta memory B',user_id='b',infer=False)['results'][0]['id']
        for tenant,expected in [('a',[aid]),('b',[bid]),('missing',[]),("a'OR'1'='1",[])]:
            assert [row['id'] for row in first.search('alpha',filters={'user_id':tenant},threshold=0)['results']]==expected
        with pytest.raises(ValueError,match='whitespace'):first.search('alpha',filters={'user_id':"a' OR 1=1 --"})
        first.update(aid,'alpha updated');assert first.get(aid)['memory']=='alpha updated'
        first.db.close();first=None
        reopened=new_memory(db,tmp_path);assert reopened.get(aid)['memory']=='alpha updated'
        assert [row['id'] for row in reopened.get_all(filters={'user_id':'a'})['results']]==[aid]
        reopened.delete(aid);assert reopened.get(aid) is None;assert reopened.get(bid)['memory']=='beta memory B'
    finally:
        for memory in [first,reopened]:
            if memory:memory.db.close()

@pytest.mark.project('mem0')
def test_mem0_invalid_batch_rollback(db):
    import pymysql
    store=vector_store(db,'atomicity')
    for vectors,ids in [([[1.,0.,0.],[1.,0.]],['first','bad_dim']),([[1.,0.,0.],[float('nan'),0.,0.]],['first','nan']),([[1.,0.,0.],[0.,1.,0.]],['duplicate','duplicate'])]:
        with pytest.raises((ValueError,pymysql.MySQLError)):store.insert(vectors,[{'user_id':'a'}]*2,ids)
        assert store.col_info()['points_count']==0
    for filters in [{'user_id':{'$in':['a']}},{'user_id':None},{"user_id') OR 1=1":'a'}]:
        with pytest.raises(NotImplementedError):store.search('alpha',[1.,0.,0.],filters=filters)

@pytest.mark.project('mem0')
def test_mem0_qdrant_cosine_equivalence(db,tmp_path):
    from mem0.vector_stores.qdrant import Qdrant
    sql=vector_store(db,'cosine');native=Qdrant(collection_name='cosine',embedding_model_dims=3,path=str(tmp_path/'qdrant'))
    ids=[str(uuid.uuid4()) for _ in range(5)]
    vectors=[[1.,0.,0.],[1.,1.,0.],[-1.,1.,0.],[-1.,0.,0.],[1.,0.,0.]];payloads=[{'user_id':'a'}]*4+[{'user_id':'b'}]
    try:
        for store in [sql,native]:store.insert(vectors=vectors,payloads=payloads,ids=ids)
        actual=sql.search('alpha',[1.,0.,0.],top_k=4,filters={'user_id':'a'})
        control=native.search('alpha',[1.,0.,0.],top_k=4,filters={'user_id':'a'})
        assert [r.id for r in actual]==[r.id for r in control]==ids[:4]
        assert [r.score for r in actual]==pytest.approx([r.score for r in control],abs=1e-6)
        assert actual[-1].score<-.99
    finally:native.client.close()

@pytest.mark.project('mem0')
def test_mem0_qdrant_typed_filter_equivalence(db,tmp_path):
    from mem0.vector_stores.qdrant import Qdrant
    sql=vector_store(db,'typed');native=Qdrant(collection_name='typed',embedding_model_dims=3,path=str(tmp_path/'qdrant'))
    values=[1,'1',True,'true'];ids=[str(uuid.uuid4()) for _ in values]
    try:
        for store in [sql,native]:store.insert(vectors=[[1.,0.,0.]]*4,payloads=[{'kind':v} for v in values],ids=ids)
        for index,value in enumerate(values):
            assert [r.id for r in sql.search('alpha',[1.,0.,0.],top_k=10,filters={'kind':value})]==[ids[index]]
            assert [r.id for r in native.search('alpha',[1.,0.,0.],top_k=10,filters={'kind':value})]==[ids[index]]
    finally:native.client.close()
