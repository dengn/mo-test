"""AgentScope 2.0 typed AgentState snapshots in MatrixOne JSON."""
import json,re
import pymysql
from agentscope.state import AgentState
class MatrixOneAgentScopeStateStore:
    def __init__(self,connection_config):
        self.config=dict(connection_config)
        self._query('CREATE TABLE IF NOT EXISTS agentscope_states(id VARCHAR(128) PRIMARY KEY,payload JSON)')
    def _query(self,sql,args=None):
        with pymysql.connect(**self.config) as connection:
            with connection.cursor() as cursor:cursor.execute(sql,args);return cursor.fetchall()
    def save(self,key,state):
        if not isinstance(state,AgentState):raise TypeError('An AgentScope AgentState is required')
        self._query('INSERT INTO agentscope_states VALUES(%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)',(key,json.dumps(state.model_dump(mode='json'),ensure_ascii=False)))
    def load(self,key):
        rows=self._query('SELECT payload FROM agentscope_states WHERE id=%s',(key,))
        return AgentState.model_validate(json.loads(rows[0][0])) if rows else None
    def delete(self,key):self._query('DELETE FROM agentscope_states WHERE id=%s',(key,))
