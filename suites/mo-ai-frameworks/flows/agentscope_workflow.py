import uuid,json,pymysql
from agentscope.tool import Toolkit,FunctionTool,ToolChunk,ToolResponse
from agentscope.message import TextBlock,ToolCallBlock,UserMsg,ToolResultState
from agentscope.state import AgentState
from adapters.agentscope_state import MatrixOneAgentScopeStateStore

async def workflow(cfg):

    def query(sql, args=None):
        with pymysql.connect(**cfg) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.fetchall()
    query('CREATE TABLE knowledge(id INT PRIMARY KEY,tenant VARCHAR(128),content TEXT)')
    query('INSERT INTO knowledge VALUES(1,%s,%s),(2,%s,%s)', ('a', 'alpha A 中文', 'b', 'beta B'))

    def retrieve(tenant: str) -> ToolChunk:
        """Retrieve knowledge for a tenant.

        Args:
            tenant: Tenant identifier used as a bound SQL parameter.
        """
        rows = query('SELECT id,tenant,content FROM knowledge WHERE tenant=%s ORDER BY id', (tenant,))
        return ToolChunk(content=[TextBlock(text=json.dumps([dict(id=r[0], tenant=r[1], content=r[2]) for r in rows], ensure_ascii=False))])
    toolkit = Toolkit(tools=[FunctionTool(retrieve, is_read_only=True)])
    state = AgentState(session_id='session_a', context=[UserMsg(name='user', content=[TextBlock(text='查询 alpha 中文')])])
    state.tool_context.activated_groups = ['basic']

    async def invoke(current, tenant, expected):
        response = None
        async for chunk in toolkit.call_tool(ToolCallBlock(id='call_' + uuid.uuid4().hex, name='retrieve', input=json.dumps({'tenant': tenant})), current):
            if isinstance(chunk, ToolResponse):
                response = chunk
        assert response is not None and response.state == ToolResultState.SUCCESS, response
        assert [row['id'] for row in json.loads(response.content[0].text)] == expected
    for tenant, expected in [('a', [1]), ('b', [2]), ('missing', []), ("a' OR 1=1 --", [])]:
        await invoke(state, tenant, expected)
    store = MatrixOneAgentScopeStateStore(cfg)
    state.cur_iter = 2
    store.save('a', state)
    store.save('b', AgentState(session_id='session_b'))
    restored = MatrixOneAgentScopeStateStore(cfg).load('a')
    assert restored.model_dump(mode='json') == state.model_dump(mode='json')
    assert restored.context[0].content[0].text == '查询 alpha 中文'
    await invoke(restored, 'b', [2])
    restored.cur_iter += 1
    store.save('a', restored)
    assert store.load('a').cur_iter == 3
    assert store.load('b').session_id == 'session_b'
    assert store.load("a' OR 1=1 --") is None
    store.delete('a')
    assert store.load('a') is None
    assert store.load('b') is not None
    return 'native Toolkit/FunctionTool/streaming ToolResponse; typed AgentState JSON save/new store model_validate/reused Toolkit; context, iteration, session isolation, upsert/delete; no complete Agent model loop'
