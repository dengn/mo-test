"""Test-only deterministic embeddings and an LLM which must never be invoked."""
from mem0.embeddings.base import EmbeddingBase
from mem0.llms.base import LLMBase
class FixtureEmbedding(EmbeddingBase):
    def embed(self,text,memory_action=None):return [0.,1.,0.] if 'beta' in text else [1.,0.,0.]
class NoCallLLM(LLMBase):
    def generate_response(self,*args,**kwargs):raise AssertionError('This fixture must not call an LLM; infer=False required')
