import asyncio,json
import pytest

@pytest.mark.project('openai-agents')
def test_openai_function_tool(knowledge):
    from agents import function_tool,set_tracing_disabled
    from agents.tool_context import ToolContext
    set_tracing_disabled(True);tool=function_tool(knowledge)
    async def run():
        for tenant,expected in [('a',[1]),('b',[2]),('missing',[])]:
            args=json.dumps({'tenant':tenant,'query_text':'alpha'})
            context=ToolContext(context=None,tool_name=tool.name,tool_call_id='call_'+tenant,tool_arguments=args)
            result=await tool.on_invoke_tool(context,args)
            result=json.loads(result) if isinstance(result,str) else result
            assert [r['id'] for r in result]==expected
    asyncio.run(run())

@pytest.mark.project('openai-agents')
def test_openai_sqlalchemy_session(db):
    from agents import set_tracing_disabled
    from adapters.openai_sqlalchemy_session import MatrixOneSQLAlchemySession
    set_tracing_disabled(True)
    async def run():
        options=dict(url=db.url('aiomysql'),create_tables=True,sessions_table='sessions',messages_table='messages')
        a=MatrixOneSQLAlchemySession.from_url('a',**options);b=MatrixOneSQLAlchemySession.from_url('b',**options)
        reopened=MatrixOneSQLAlchemySession.from_url('a',**options)
        try:
            await a.add_items([{'role':'user','content':'你好'},{'role':'assistant','content':'回答'}])
            await b.add_items([{'role':'user','content':'other'}])
            assert [item['content'] for item in await reopened.get_items()]==['你好','回答']
            await a.clear_session();assert await reopened.get_items()==[]
            assert [item['content'] for item in await b.get_items()]==['other']
        finally:
            for session in [a,b,reopened]:await session._engine.dispose()
    asyncio.run(run())
    with pytest.raises(ValueError):MatrixOneSQLAlchemySession('x'*256,engine=None)

@pytest.mark.project('pydantic-ai')
def test_pydantic_ai_agent_tool_return(knowledge):
    from pydantic_ai import Agent
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart,ToolReturnPart,TextPart
    for tenant,expected in [('a',[1]),('b',[2]),('missing',[])]:
        def model(messages,info):
            returns=[part for message in messages for part in getattr(message,'parts',[]) if isinstance(part,ToolReturnPart)]
            if returns:return ModelResponse(parts=[TextPart(json.dumps(returns[-1].content))])
            return ModelResponse(parts=[ToolCallPart(knowledge.__name__,{'tenant':tenant,'query_text':'alpha'})])
        agent=Agent(model=FunctionModel(model),tools=[knowledge])
        assert [row['id'] for row in json.loads(agent.run_sync('retrieve knowledge').output)]==expected

@pytest.mark.project('google-adk')
def test_adk_function_tool(knowledge):
    from google.adk.tools import FunctionTool
    tool=FunctionTool(func=knowledge)
    async def run():
        for tenant,expected in [('a',[1]),('b',[2]),('missing',[])]:
            result=await tool.run_async(args={'tenant':tenant,'query_text':'alpha'},tool_context=None)
            assert [row['id'] for row in result]==expected
    asyncio.run(run())

@pytest.mark.project('google-adk')
def test_adk_database_session(db):
    from google.adk.sessions import DatabaseSessionService
    from google.adk.events import Event,EventActions
    async def run():
        service=DatabaseSessionService(db_url=db.url('aiomysql'));reopened=None
        try:
            session=await service.create_session(app_name='regression',user_id='a',session_id='session',state={'x':1})
            await service.append_event(session,Event(invocation_id='inv',author='agent',actions=EventActions(state_delta={'x':2})))
            reopened=DatabaseSessionService(db_url=db.url('aiomysql'))
            result=await reopened.get_session(app_name='regression',user_id='a',session_id='session')
            assert result.state['x']==2;assert len(result.events)==1
            assert await reopened.get_session(app_name='regression',user_id='b',session_id='session') is None
        finally:
            await service.db_engine.dispose()
            if reopened:await reopened.db_engine.dispose()
    asyncio.run(run())
