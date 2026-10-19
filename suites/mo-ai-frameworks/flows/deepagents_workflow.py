from pydantic import Field
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage,HumanMessage,ToolMessage
from langgraph.types import Command
from adapters.langgraph_checkpoint import MatrixOneSaver

class FixtureModel(FakeMessagesListChatModel):
    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, *args, **kwargs)

def tool_response(name, args, id):
    return AIMessage(content='', tool_calls=[dict(name=name, args=args, id=id, type='tool_call')])

def graph(model, saver, **kwargs):
    return create_deep_agent(model=model, checkpointer=saver, subagents=[], **kwargs)

def filesystem_lifecycle(factory):
    config = {'configurable': {'thread_id': 'files_a'}}
    other = {'configurable': {'thread_id': 'files_b'}}
    first = graph(FixtureModel(responses=[tool_response('write_file', {'file_path': '/memo.txt', 'content': 'alpha 中文'}, 'write'), AIMessage(content='written')]), factory())
    result = first.invoke({'messages': [HumanMessage(content='Write a memo')]}, config)
    assert result['files']['/memo.txt']['content'] == 'alpha 中文', result
    assert any((isinstance(m, ToolMessage) and m.name == 'write_file' and (m.status != 'error') for m in result['messages']))
    model = FixtureModel(responses=[tool_response('read_file', {'file_path': '/memo.txt'}, 'read'), AIMessage(content='restored')])
    reopened = graph(model, factory())
    assert reopened.get_state(config).values['files'] == result['files']
    resumed = reopened.invoke({'messages': [HumanMessage(content='Read the saved memo')]}, config)
    assert any((isinstance(m, ToolMessage) and m.name == 'read_file' and ('alpha 中文' in str(m.content)) for m in resumed['messages']))
    assert any((isinstance(m, ToolMessage) and m.name == 'read_file' and ('alpha 中文' in str(m.content)) for m in model.seen[-1]))
    isolated = graph(FixtureModel(responses=[tool_response('read_file', {'file_path': '/memo.txt'}, 'missing'), AIMessage(content='missing')]), factory())
    missing = isolated.invoke({'messages': [HumanMessage(content='Read memo')]}, other)
    assert '/memo.txt' not in missing.get('files', {})
    assert all(('alpha 中文' not in str(m.content) for m in missing['messages']))
    assert reopened.get_state({'configurable': {'thread_id': "files_a' OR 1=1 --"}}).values == {}
    saver = factory()
    assert len(list(saver.list(config))) >= 3
    saver.delete_thread('files_a')
    assert graph(model, factory()).get_state(config).values == {}
    assert isolated.get_state(other).values['messages']
    return 'native create_deep_agent/write_file/read_file; files and messages reloaded from new saver/graph, persisted content reaches next model request; thread isolation/history/delete; StateBackend, deterministic model; no cross-thread StoreBackend/async/subagent/concurrency certification'

def approval_lifecycle(factory):
    config = {'configurable': {'thread_id': 'approval'}}
    model = FixtureModel(responses=[tool_response('write_file', {'file_path': '/approved.txt', 'content': 'approved 中文'}, 'approval_write'), AIMessage(content='written')])
    agent = graph(model, factory(), interrupt_on={'write_file': True})
    paused = agent.invoke({'messages': [HumanMessage(content='Write after approval')]}, config)
    assert paused.get('__interrupt__'), paused
    assert '/approved.txt' not in paused.get('files', {})
    restored = graph(FixtureModel(responses=[AIMessage(content='approved')]), factory(), interrupt_on={'write_file': True})
    result = restored.invoke(Command(resume={'decisions': [{'type': 'approve'}]}), config)
    assert result['files']['/approved.txt']['content'] == 'approved 中文', result
    assert not result.get('__interrupt__')
    return 'native DeepAgents human-in-the-loop interrupt before write; new graph/saver resumes approval and executes pending filesystem tool; deterministic model'

def sql_factory(cfg):

    def factory():
        saver = MatrixOneSaver(cfg)
        saver.setup()
        return saver
    return factory
