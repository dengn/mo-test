"""CrewAI synchronous FlowPersistence prototype: append-only JSON snapshots."""
import json
import pymysql
from pydantic import BaseModel,PrivateAttr
from crewai.flow.persistence.base import FlowPersistence

class MatrixOneFlowPersistence(FlowPersistence):
    persistence_type:str='matrixone'
    _config:dict=PrivateAttr()
    def __init__(self,connection_config):
        super().__init__();self._config=dict(connection_config);self.init_db()
    def _query(self,sql,args=None):
        with pymysql.connect(**self._config) as connection:
            with connection.cursor() as cursor:cursor.execute(sql,args);return cursor.fetchall()
    def init_db(self):
        self._query('CREATE TABLE IF NOT EXISTS crewai_flow_states(id BIGINT AUTO_INCREMENT PRIMARY KEY,flow_uuid VARCHAR(36),method_name VARCHAR(255),state_json JSON,KEY idx_flow(flow_uuid))')
    def save_state(self,flow_uuid,method_name,state_data):
        if isinstance(state_data,BaseModel):state_data=state_data.model_dump(mode='json')
        if not isinstance(state_data,dict):raise TypeError('Flow state must be a dict or BaseModel')
        self._query('INSERT INTO crewai_flow_states(flow_uuid,method_name,state_json) VALUES(%s,%s,%s)',(flow_uuid,method_name,json.dumps(state_data,ensure_ascii=False,allow_nan=False)))
    def load_state(self,flow_uuid):
        rows=self._query('SELECT state_json FROM crewai_flow_states WHERE flow_uuid=%s ORDER BY id DESC LIMIT 1',(flow_uuid,))
        return json.loads(rows[0][0]) if rows else None
    def save_pending_feedback(self,*args,**kwargs):raise NotImplementedError('Human feedback persistence is outside this prototype')
    def load_pending_feedback(self,*args,**kwargs):raise NotImplementedError('Human feedback persistence is outside this prototype')
    def clear_pending_feedback(self,*args,**kwargs):raise NotImplementedError('Human feedback persistence is outside this prototype')
