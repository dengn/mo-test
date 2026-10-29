"""Small synchronous LiteLLM CustomLogger bridge; stores selected response fields."""
import json,threading,asyncio
import pymysql
from litellm.integrations.custom_logger import CustomLogger

class MatrixOneLiteLLMLogger(CustomLogger):
    def __init__(self,connection_config):
        super().__init__();self.connection_config=dict(connection_config)
        self.completed=threading.Event();self.errors=[];self.last_event=None
        self._query('CREATE TABLE IF NOT EXISTS llm_events(tenant VARCHAR(128),event_id VARCHAR(255),payload JSON,PRIMARY KEY(tenant,event_id))')
    def _query(self,sql,args=None):
        with pymysql.connect(**self.connection_config) as c:
            with c.cursor() as q:q.execute(sql,args);return q.fetchall()
    def log_success_event(self,kwargs,response_obj,start_time,end_time):
        try:
            metadata=kwargs.get('litellm_params',{}).get('metadata') or {}
            tenant=metadata.get('tenant')
            if not isinstance(tenant,str) or not tenant or len(tenant)>128:raise ValueError('A tenant identifier up to 128 characters is required')
            payload={'model':response_obj.model,'choices':[c.model_dump(mode='json') for c in response_obj.choices],'usage':response_obj.usage.model_dump(mode='json') if response_obj.usage else None}
            self._query('INSERT INTO llm_events VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)',(tenant,response_obj.id,json.dumps(payload,ensure_ascii=False)))
            self.last_event=(kwargs,response_obj,start_time,end_time)
        except Exception as e:self.errors.append(str(e))
        finally:self.completed.set()
    async def async_log_success_event(self,kwargs,response_obj,start_time,end_time):
        await asyncio.to_thread(self.log_success_event,kwargs,response_obj,start_time,end_time)
    def list_events(self,tenant):
        return [{'id':r[0],'payload':json.loads(r[1])} for r in self._query('SELECT event_id,payload FROM llm_events WHERE tenant=%s ORDER BY event_id',(tenant,))]
