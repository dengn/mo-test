import json,pymysql
from types import SimpleNamespace
from swarm import Swarm,Agent
from swarm.types import Result
from openai.types.chat import ChatCompletion
from adapters.framework_json import MatrixOneJsonSnapshots

class FixtureClient:

    def __init__(self, tenant):
        self.tenant = tenant
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **params):
        self.requests.append(params)
        if len(self.requests) == 1:
            properties = params['tools'][0]['function']['parameters']['properties']
            assert 'context_variables' not in properties
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'lookup_call', 'type': 'function', 'function': {'name': 'retrieve', 'arguments': json.dumps({'tenant': self.tenant})}}]}
        else:
            data = json.loads(params['messages'][-1]['content'])
            message = {'role': 'assistant', 'content': json.dumps({'ids': [row['id'] for row in data]})}
        return ChatCompletion(id='fixture', object='chat.completion', created=1, model='fixture', choices=[{'index': 0, 'finish_reason': 'stop', 'message': message}])

def swarm_lifecycle(lookup, factory):

    def retrieve(tenant: str, context_variables: dict) -> Result:
        """Retrieve exact tenant-scoped knowledge using a bound SQL parameter."""
        return Result(value=json.dumps(lookup(tenant), ensure_ascii=False), agent=handoff, context_variables={'last_tenant': tenant, 'calls': context_variables.get('calls', 0) + 1})
    handoff = Agent(name='continuation', functions=[retrieve])
    start = Agent(name='entry', functions=[retrieve])
    for tenant, expected in [('a', [1]), ('b', [2]), ('missing', []), ("a' OR 1=1 --", [])]:
        client = FixtureClient(tenant)
        messages = [{'role': 'user', 'content': 'Retrieve alpha 中文'}]
        response = Swarm(client=client).run(agent=start, messages=messages, context_variables={'calls': 0}, max_turns=5)
        assert response.agent.name == 'continuation'
        assert json.loads(response.messages[-1]['content'])['ids'] == expected
        assert response.context_variables['last_tenant'] == tenant and response.context_variables['calls'] == 1
        assert len(client.requests) == 2 and client.requests[-1]['messages'][-1]['role'] == 'tool'
        if tenant == 'a':
            state = {'messages': messages + response.messages, 'context_variables': response.context_variables, 'agent_name': response.agent.name}
            factory('a').save('conversation', state)
    factory('b').save('conversation', {'tenant': 'b'})
    saved = factory('a').load('conversation')
    assert saved['context_variables']['calls'] == 1
    assert factory("a' OR 1=1 --").load('conversation') is None
    resumed_client = FixtureClient('a')
    history = saved['messages'] + [{'role': 'user', 'content': 'Continue'}]
    response = Swarm(client=resumed_client).run(agent=Agent(name=saved['agent_name'], functions=[retrieve]), messages=history, context_variables=saved['context_variables'], max_turns=5)
    assert response.context_variables['calls'] == 2
    assert json.loads(response.messages[-1]['content'])['ids'] == [1]
    assert any((m.get('role') == 'tool' and 'alpha A 中文' in m.get('content', '') for m in resumed_client.requests[0]['messages']))
    factory('a').save('conversation', {'messages': history + response.messages, 'context_variables': response.context_variables, 'agent_name': response.agent.name})
    assert factory('a').load('conversation')['context_variables']['calls'] == 2
    assert [m for m in factory('a').load('conversation')['messages'] if m['role'] == 'user'][-1]['content'] == 'Continue'
    factory('a').delete('conversation')
    assert factory('a').load('conversation') is None
    assert factory('b').load('conversation') == {'tenant': 'b'}
    return 'pinned native Swarm.run/schema/tool dispatch/Result context and Agent handoff; parameterized tenant SQL; custom JSON conversation checkpoint reopens and feeds old tool history into new Swarm request; native in-memory lookup/file reference; model fixture, no built-in Swarm persistence or real inference claim'

def sql_workflow(cfg):

    def query(sql, args=None):
        with pymysql.connect(**cfg) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.fetchall()
    query('CREATE TABLE swarm_knowledge(id INT PRIMARY KEY,tenant VARCHAR(128),content TEXT)')
    query('INSERT INTO swarm_knowledge VALUES(1,%s,%s),(2,%s,%s)', ('a', 'alpha A 中文', 'b', 'beta B'))

    def lookup(tenant):
        return [dict(id=r[0], tenant=r[1], content=r[2]) for r in query('SELECT id,tenant,content FROM swarm_knowledge WHERE tenant=%s ORDER BY id', (tenant,))]
    return swarm_lifecycle(lookup, lambda tenant: MatrixOneJsonSnapshots(cfg, tenant))
