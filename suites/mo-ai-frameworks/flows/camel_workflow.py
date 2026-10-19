from camel.agents import ChatAgent
from camel.models import StubModel
from camel.types import ModelType
from camel.memories import ChatHistoryMemory,ScoreBasedContextCreator

class CaptureStub(StubModel):

    def _run(self, messages, *args, **kwargs):
        self.seen = list(messages)
        return super()._run(messages, *args, **kwargs)

def lifecycle(factory):

    def memory(storage, model):
        return ChatHistoryMemory(ScoreBasedContextCreator(model.token_counter, 4096), storage=storage, agent_id='fixture_agent')
    store = factory('a')
    model = CaptureStub(ModelType.STUB)
    first = ChatAgent(model=model, memory=memory(store, model), agent_id='fixture_agent', summarize_threshold=None)
    assert first.step('记住 alpha 中文').msg.content == 'Lorem Ipsum'
    before = store.load()
    assert len(before) == 2
    reopened = factory('a')
    assert reopened.load() == before
    restored_model = CaptureStub(ModelType.STUB)
    restored = ChatAgent(model=restored_model, agent_id='fixture_agent', summarize_threshold=None)
    restored.memory = memory(reopened, restored_model)
    assert restored.memory.get_context()[0][0]['content'] == '记住 alpha 中文'
    assert restored.step('继续 beta').msg.content == 'Lorem Ipsum'
    assert any((m.get('content') == '记住 alpha 中文' for m in restored_model.seen))
    assert len(reopened.load()) == 4
    other = factory('b')
    other.save([{'tenant': 'b', 'text': '独立'}])
    assert factory("a' OR 1=1 --").load() == []
    assert factory('b').load() == [{'tenant': 'b', 'text': '独立'}]
    reopened.clear()
    assert reopened.load() == []
    assert factory('b').load() == other.load()
    return 'native ChatAgent.step + ChatHistoryMemory; public memory setter restores new client, saved context reaches next model request; Unicode/order/namespace/clear; native JsonStorage reference, StubModel, no real inference or concurrent writers'
