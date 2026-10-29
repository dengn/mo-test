"""AG-UI typed event journal; cursor IDs belong to this storage adapter."""
import json
import pymysql
from pydantic import TypeAdapter
from ag_ui.core import Event
VALIDATE=TypeAdapter(Event)

class MatrixOneAGUIJournal:
    def __init__(self,cfg,tenant):
        if not isinstance(tenant,str) or not tenant or len(tenant)>128:raise ValueError('Invalid tenant')
        self.cfg=dict(cfg);self.tenant=tenant
        self._query('CREATE TABLE IF NOT EXISTS ag_ui_journal(id BIGINT AUTO_INCREMENT PRIMARY KEY,tenant VARCHAR(128),run_id VARCHAR(128),payload JSON,INDEX(tenant,run_id))')
    def _query(self,sql,args=None):
        with pymysql.connect(**self.cfg) as connection:
            with connection.cursor() as cursor:cursor.execute(sql,args);return cursor.fetchall()
    def append_batch(self,run_id,events):
        if not isinstance(run_id,str) or not run_id or len(run_id)>128:raise ValueError('Invalid run_id')
        values=[]
        for event in events:
            typed=VALIDATE.validate_python(event)
            payload=json.dumps(typed.model_dump(mode='json',by_alias=True,exclude_none=True),ensure_ascii=False,allow_nan=False)
            values.append((self.tenant,run_id,payload))
        if not values:return
        with pymysql.connect(**self.cfg) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:cursor.executemany('INSERT INTO ag_ui_journal(tenant,run_id,payload) VALUES(%s,%s,%s)',values)
                connection.commit()
            except BaseException:connection.rollback();raise
    def replay(self,run_id,after_id=0):
        if not isinstance(after_id,int) or after_id<0:raise ValueError('Invalid cursor')
        rows=self._query('SELECT id,payload FROM ag_ui_journal WHERE tenant=%s AND run_id=%s AND id>%s ORDER BY id',(self.tenant,run_id,after_id))
        return [(row[0],VALIDATE.validate_json(row[1])) for row in rows]
    def delete(self,run_id):self._query('DELETE FROM ag_ui_journal WHERE tenant=%s AND run_id=%s',(self.tenant,run_id))
