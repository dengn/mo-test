import asyncio,importlib,uuid
from functools import partial
import pytest

class CharacterTokenizer:
    def encode(self,text):return [ord(character) for character in text]
    def decode(self,tokens):return ''.join(chr(token) for token in tokens)

def rag_lifecycle(db,tmp_path,backend):
    import numpy as np
    from lightrag import LightRAG,QueryParam
    from lightrag.utils import EmbeddingFunc,Tokenizer
    from lightrag.kg.shared_storage import initialize_share_data
    from adapters.lightrag_storage import MatrixOneKVStorage,MatrixOneVectorStorage
    calls=[];workspace_prefix='r_'+uuid.uuid4().hex[:10]
    async def embed(texts,**kwargs):return np.array([[0.,1.,0.] if 'beta' in text.lower() else [1.,0.,0.] for text in texts],dtype=np.float32)
    async def llm(prompt,**kwargs):calls.append(prompt);return '<|COMPLETE|>'
    def build(workspace):
        module=importlib.import_module('lightrag.lightrag');original=module.get_storage_class
        def factory(name):
            if name=='JsonKVStorage':return partial(MatrixOneKVStorage,connection_config=db.config)
            if name=='NanoVectorDBStorage':return partial(MatrixOneVectorStorage,connection_config=db.config)
            return original(name)
        try:
            if backend=='matrixone':module.get_storage_class=factory
            return LightRAG(working_dir=str(tmp_path),workspace=workspace_prefix+'_'+workspace,llm_model_func=llm,embedding_func=EmbeddingFunc(embedding_dim=3,max_token_size=4096,func=embed,model_name='fixture3'),tokenizer=Tokenizer('fixture-character',CharacterTokenizer()),entity_extract_max_gleaning=0,enable_llm_cache=False,enable_llm_cache_for_entity_extract=False)
        finally:module.get_storage_class=original
    async def retrieve(rag,query):
        result=await rag.aquery_data(query,QueryParam(mode='naive',top_k=1,chunk_top_k=1,enable_rerank=False))
        return [chunk['content'] for chunk in result.get('data',{}).get('chunks',[])]
    async def run():
        initialize_share_data(workers=1);rag=other=reopened=None
        try:
            rag=build('a');await rag.initialize_storages()
            await rag.ainsert(['Alpha document A 中文','Beta document B'],ids=['doc_alpha','doc_beta'])
            counts=await rag.doc_status.get_status_counts();assert counts.get('processed')==2 and not counts.get('failed'),counts
            assert await retrieve(rag,'alpha')==['Alpha document A 中文']
            assert await retrieve(rag,'beta')==['Beta document B']
            other=build('other');await other.initialize_storages();assert await retrieve(other,'alpha')==[]
            await other.ainsert('Private document other',ids='doc_other')
            assert await retrieve(other,'alpha')==['Private document other']
            assert await retrieve(rag,'alpha')==['Alpha document A 中文']
            await rag.finalize_storages();rag=None
            reopened=build('a');await reopened.initialize_storages()
            assert await retrieve(reopened,'alpha')==['Alpha document A 中文']
            await reopened.adelete_by_doc_id('doc_alpha')
            assert await reopened.full_docs.get_by_id('doc_alpha') is None
            assert await retrieve(reopened,'alpha')==[]
            assert await retrieve(reopened,'beta')==['Beta document B'];assert len(calls)==3
        finally:
            for instance in [rag,other,reopened]:
                if instance:await instance.finalize_storages()
    asyncio.run(run())

@pytest.mark.project('lightrag')
def test_lightrag_matrixone_ingest_query_delete(db,tmp_path):rag_lifecycle(db,tmp_path,'matrixone')

@pytest.mark.project('lightrag')
def test_lightrag_native_reference(db,tmp_path):rag_lifecycle(db,tmp_path,'native_files')
