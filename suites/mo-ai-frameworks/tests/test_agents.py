import asyncio,json
import pytest

@pytest.mark.project('autogen')
def test_autogen_function_tool(knowledge):
    from autogen_core.tools import FunctionTool
    from autogen_core import CancellationToken
    tool=FunctionTool(knowledge,description='Retrieve MatrixOne knowledge')
    async def run():
        for tenant,expected in [('a',[1]),('b',[2]),('missing',[])]:
            result=await tool.run_json({'tenant':tenant,'query_text':'alpha'},CancellationToken())
            assert [row['id'] for row in result]==expected
    asyncio.run(run())

@pytest.mark.project('autogen')
def test_autogen_state_save_load_resume(db):
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.replay import ReplayChatCompletionClient
    db.query('CREATE TABLE snapshots(id VARCHAR(64) PRIMARY KEY,state JSON)')
    async def run():
        original_client=ReplayChatCompletionClient(chat_completions=['记忆已接收'])
        restored_client=ReplayChatCompletionClient(chat_completions=['继续执行'])
        try:
            original=AssistantAgent('regression_agent',model_client=original_client)
            assert (await original.run(task='记住 alpha')).messages[-1].content=='记忆已接收'
            state=await original.save_state();db.query('INSERT INTO snapshots VALUES(%s,%s)',('a',json.dumps(state,ensure_ascii=False)))
            db.query('INSERT INTO snapshots VALUES(%s,%s)',('b',json.dumps({'tenant':'b'})))
            saved=json.loads(db.query('SELECT state FROM snapshots WHERE id=%s',('a',))[0][0])
            restored=AssistantAgent('regression_agent',model_client=restored_client);await restored.load_state(saved)
            assert await restored.save_state()==state
            assert (await restored.run(task='继续')).messages[-1].content=='继续执行'
            assert len((await restored.save_state())['llm_context']['messages'])>len(state['llm_context']['messages'])
            assert json.loads(db.query('SELECT state FROM snapshots WHERE id=%s',('b',))[0][0])=={'tenant':'b'}
        finally:await original_client.close();await restored_client.close()
    asyncio.run(run())

@pytest.mark.project('semantic-kernel')
def test_semantic_kernel_plugin_invoke(knowledge):
    from semantic_kernel import Kernel
    from semantic_kernel.functions import kernel_function,KernelArguments
    class Plugin:
        @kernel_function(name='retrieve',description='Retrieve tenant-scoped MatrixOne knowledge')
        def retrieve(self,tenant:str,query_text:str)->str:return json.dumps(knowledge(tenant,query_text),ensure_ascii=False)
    async def run():
        kernel=Kernel();kernel.add_plugin(Plugin(),plugin_name='matrixone')
        for tenant,expected in [('a',[1]),('b',[2]),('missing',[])]:
            result=await kernel.invoke(plugin_name='matrixone',function_name='retrieve',arguments=KernelArguments(tenant=tenant,query_text='alpha'))
            assert [row['id'] for row in json.loads(str(result))]==expected
    asyncio.run(run())
