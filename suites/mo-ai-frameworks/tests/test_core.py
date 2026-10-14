import pytest

@pytest.mark.project('langchain')
def test_langchain_chat_history(db):
    from sqlalchemy import create_engine
    from langchain_community.chat_message_histories import SQLChatMessageHistory
    first=create_engine(db.url());second=create_engine(db.url())
    try:
        a=SQLChatMessageHistory(session_id='a',connection=first,table_name='messages')
        b=SQLChatMessageHistory(session_id='b',connection=first,table_name='messages')
        a.add_user_message('你好');a.add_ai_message('回答');b.add_user_message('other')
        reopened=SQLChatMessageHistory(session_id='a',connection=second,table_name='messages')
        assert [m.content for m in reopened.messages]==['你好','回答']
        a.clear();assert reopened.messages==[];assert [m.content for m in b.messages]==['other']
    finally:first.dispose();second.dispose()

@pytest.mark.project('langchain')
def test_langchain_sql_tool(db):
    from sqlalchemy import create_engine
    from langchain_community.utilities import SQLDatabase
    from langchain_community.tools.sql_database.tool import QuerySQLDatabaseTool
    db.query('CREATE TABLE items(id INT PRIMARY KEY,value VARCHAR(128))')
    db.query('INSERT INTO items VALUES(%s,%s)',(1,'中文'))
    engine=create_engine(db.url())
    try:
        database=SQLDatabase(engine,include_tables=['items'])
        assert 'items' in database.get_table_info()
        assert QuerySQLDatabaseTool(db=database).invoke({'query':'SELECT value FROM items ORDER BY id'})=="[('中文',)]"
    finally:engine.dispose()

@pytest.mark.project('langchain')
def test_langchain_filtered_retriever(db):
    from langchain_core.embeddings import Embeddings
    from adapters.vector_store import FilteredMatrixOneVectorStore
    class FixedEmbedding(Embeddings):
        def embed_query(self,text):return [0.,1.,0.] if 'beta' in text else [1.,0.,0.]
        def embed_documents(self,texts):return [self.embed_query(t) for t in texts]
    store=FilteredMatrixOneVectorStore(embedding=FixedEmbedding(),connection_args=db.sdk_config,table_name='vectors')
    try:
        store.add_texts(['alpha A','beta B'],metadatas=[{'tenant':'a'},{'tenant':'b'}],ids=['a','b'])
        assert [d.page_content for d in store.similarity_search('alpha',k=1,filter={'tenant':'b'})]==['beta B']
        assert [d.page_content for d in store.as_retriever(search_kwargs={'k':1,'filter':{'tenant':'a'}}).invoke('beta')]==['alpha A']
        with pytest.raises(NotImplementedError):store.similarity_search('alpha',filter={'tenant':{'$in':['a']}})
        store.delete(['a']);assert [d.page_content for d in store.similarity_search('alpha',k=10)]==['beta B']
    finally:store.client.disconnect()

@pytest.mark.project('llamaindex')
def test_llamaindex_index_retriever_delete(db):
    from adapters.vector_store import ExactStore,LlamaMatrixOneStore
    from llama_index.core import VectorStoreIndex
    from llama_index.core.schema import TextNode,NodeRelationship,RelatedNodeInfo
    from llama_index.core.embeddings import BaseEmbedding
    from llama_index.core.vector_stores.types import VectorStoreQuery
    class Embedding(BaseEmbedding):
        def _get_query_embedding(self,q):return [1.,0.,0.]
        def _get_text_embedding(self,t):return [1.,0.,0.]
        async def _aget_query_embedding(self,q):return self._get_query_embedding(q)
    store=LlamaMatrixOneStore(ExactStore(db.config,'vectors'))
    nodes=[TextNode(id_='a',text='alpha',embedding=[1.,0.,0.],relationships={NodeRelationship.SOURCE:RelatedNodeInfo(node_id='doc-a')}),TextNode(id_='b',text='beta',embedding=[0.,1.,0.])]
    assert store.add(nodes)==['a','b']
    index=VectorStoreIndex.from_vector_store(store,embed_model=Embedding())
    assert index.as_retriever(similarity_top_k=1).retrieve('alpha')[0].node.text=='alpha'
    store.delete('doc-a');assert index.as_retriever(similarity_top_k=1).retrieve('alpha')[0].node.text=='beta'
    for args in [{'doc_ids':['doc-a']},{'node_ids':['a']}]:
        with pytest.raises(NotImplementedError):store.query(VectorStoreQuery(query_embedding=[1.,0.,0.],**args))

@pytest.mark.project('haystack')
def test_haystack_pipeline_filter_delete(db):
    from adapters.vector_store import ExactStore,HaystackMatrixOneStore
    from haystack import Pipeline,Document,component
    from haystack.components.writers import DocumentWriter
    store=HaystackMatrixOneStore(ExactStore(db.config,'vectors'))
    writer=Pipeline();writer.add_component('writer',DocumentWriter(document_store=store))
    result=writer.run({'writer':{'documents':[Document(id='a',content='alpha',meta={'tenant':'a'},embedding=[1.,0.,0.]),Document(id='b',content='beta',meta={'tenant':'b'},embedding=[0.,1.,0.])]}})
    assert result['writer']['documents_written']==2;assert store.count_documents()==2
    assert [d.id for d in store.filter_documents({'field':'meta.tenant','operator':'==','value':'b'})]==['b']
    @component
    class Retriever:
        @component.output_types(documents=list[Document])
        def run(self,query_embedding:list[float],tenant:str):return {'documents':store.embedding_retrieval(query_embedding,top_k=1,tenant=tenant)}
    retriever=Pipeline();retriever.add_component('retriever',Retriever())
    assert retriever.run({'retriever':{'query_embedding':[1.,0.,0.],'tenant':'b'}})['retriever']['documents'][0].id=='b'
    store.delete_documents(['a']);assert store.count_documents()==1
