"""Small, namespace-isolated JSON snapshots used by framework integrations."""
import json,hashlib
from pathlib import Path
import pymysql

class MatrixOneJsonSnapshots:
    def __init__(self,cfg,namespace):
        if not isinstance(namespace,str) or not namespace or len(namespace)>128:raise ValueError('Invalid namespace')
        self.cfg=dict(cfg);self.namespace=namespace
        self._query('CREATE TABLE IF NOT EXISTS ai_framework_snapshots(namespace VARCHAR(128),id VARCHAR(128),payload JSON,PRIMARY KEY(namespace,id))')
    def _query(self,sql,args=None):
        with pymysql.connect(**self.cfg) as connection:
            with connection.cursor() as cursor:cursor.execute(sql,args);return cursor.fetchall()
    def save(self,key,value):
        if not isinstance(key,str) or not key or len(key)>128:raise ValueError('Invalid key')
        payload=json.dumps(value,ensure_ascii=False,allow_nan=False)
        self._query('INSERT INTO ai_framework_snapshots VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)',(self.namespace,key,payload))
    def load(self,key):
        rows=self._query('SELECT payload FROM ai_framework_snapshots WHERE namespace=%s AND id=%s',(self.namespace,key))
        return json.loads(rows[0][0]) if rows else None
    def delete(self,key):self._query('DELETE FROM ai_framework_snapshots WHERE namespace=%s AND id=%s',(self.namespace,key))

class FileJsonSnapshots:
    def __init__(self,directory,namespace):self.directory=Path(directory);self.namespace=namespace;self.directory.mkdir(parents=True,exist_ok=True)
    def _path(self,key):return self.directory/(hashlib.sha256((self.namespace+'\0'+key).encode()).hexdigest()+'.json')
    def save(self,key,value):self._path(key).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
    def load(self,key):
        p=self._path(key);return json.loads(p.read_text()) if p.exists() else None
    def delete(self,key):self._path(key).unlink(missing_ok=True)
