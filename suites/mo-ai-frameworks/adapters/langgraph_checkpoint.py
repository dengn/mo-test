"""Synchronous MatrixOne checkpoint prototype using the public LangGraph saver contract.

No JSON_TABLE, stored generated columns or SQL query text rewriting.
Separate typed checkpoint/metadata blobs and pending writes preserve serializer semantics.
Async APIs, metadata filtering and production multi-writer tuning are not implemented.
"""
import hashlib,json,uuid
from typing import Iterator
import pymysql
from langgraph.checkpoint.base import BaseCheckpointSaver,CheckpointTuple,WRITES_IDX_MAP

class MatrixOneSaver(BaseCheckpointSaver):
    def __init__(self,cfg,serde=None):
        super().__init__(serde=serde);self.cfg=dict(cfg)
    def _db(self):return pymysql.connect(**self.cfg)
    def setup(self):
        c=self._db()
        try:
            with c.cursor() as q:
                q.execute('CREATE TABLE IF NOT EXISTS mo_checkpoints(thread_id VARCHAR(150),ns_hash VARCHAR(64),ns TEXT,id VARCHAR(150),parent_id VARCHAR(150),cp_type VARCHAR(100),cp LONGBLOB,meta_type VARCHAR(100),meta LONGBLOB,PRIMARY KEY(thread_id,ns_hash,id))')
                q.execute('CREATE TABLE IF NOT EXISTS mo_writes(thread_id VARCHAR(150),ns_hash VARCHAR(64),id VARCHAR(150),task_id VARCHAR(150),idx INT,channel VARCHAR(150),value_type VARCHAR(100),value LONGBLOB,PRIMARY KEY(thread_id,ns_hash,id,task_id,idx))')
            c.commit()
        finally:c.close()
    def _key(self,config):
        v=config['configurable'];ns=v.get('checkpoint_ns','')
        return v['thread_id'],hashlib.sha256(ns.encode()).hexdigest(),ns,v.get('checkpoint_id')
    def put(self,config,checkpoint,metadata,new_versions):
        thread,h,ns,parent=self._key(config);typ,blob=self.serde.dumps_typed(checkpoint);mtyp,mblob=self.serde.dumps_typed(metadata)
        c=self._db()
        try:
            with c.cursor() as q:q.execute('INSERT INTO mo_checkpoints VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cp_type=VALUES(cp_type),cp=VALUES(cp),meta_type=VALUES(meta_type),meta=VALUES(meta)',(thread,h,ns,checkpoint['id'],parent,typ,blob,mtyp,mblob))
            c.commit()
        finally:c.close()
        return {'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':checkpoint['id']}}
    def put_writes(self,config,writes,task_id,task_path=''):
        thread,h,ns,id=self._key(config);c=self._db()
        try:
            with c.cursor() as q:
                for i,(channel,value) in enumerate(writes):
                    idx=WRITES_IDX_MAP.get(channel,i);typ,blob=self.serde.dumps_typed(value)
                    stmt='INSERT INTO mo_writes VALUES(%s,%s,%s,%s,%s,%s,%s,%s)'
                    stmt+=(' ON DUPLICATE KEY UPDATE channel=VALUES(channel),value_type=VALUES(value_type),value=VALUES(value)' if idx<0 else ' ON DUPLICATE KEY UPDATE task_id=VALUES(task_id)')
                    q.execute(stmt,(thread,h,id,task_id,idx,channel,typ,blob))
            c.commit()
        finally:c.close()
    def get_tuple(self,config):
        thread,h,ns,id=self._key(config);c=self._db()
        try:
            with c.cursor() as q:
                stmt='SELECT id,parent_id,cp_type,cp,meta_type,meta FROM mo_checkpoints WHERE thread_id=%s AND ns_hash=%s';args=[thread,h]
                if id is not None:stmt+=' AND id=%s';args.append(id)
                q.execute(stmt+' ORDER BY id DESC LIMIT 1',tuple(args));r=q.fetchone()
                if r is None:return None
                q.execute('SELECT task_id,channel,value_type,value FROM mo_writes WHERE thread_id=%s AND ns_hash=%s AND id=%s ORDER BY task_id,idx',(thread,h,r[0]));w=q.fetchall()
            conf={'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':r[0]}}
            parent={'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':r[1]}} if r[1] else None
            return CheckpointTuple(config=conf,checkpoint=self.serde.loads_typed((r[2],bytes(r[3]))),metadata=self.serde.loads_typed((r[4],bytes(r[5]))),parent_config=parent,pending_writes=[(v[0],v[1],self.serde.loads_typed((v[2],bytes(v[3])))) for v in w])
        finally:c.close()
    def list(self,config,*,filter=None,before=None,limit=None):
        if filter:raise NotImplementedError('Metadata filter not implemented')
        if config is None:raise NotImplementedError('Cross-thread listing not implemented')
        thread,h,ns,id=self._key(config);c=self._db()
        try:
            with c.cursor() as q:
                stmt='SELECT id FROM mo_checkpoints WHERE thread_id=%s AND ns_hash=%s';args=[thread,h]
                if before:stmt+=' AND id<%s';args.append(before['configurable']['checkpoint_id'])
                if id:stmt+=' AND id=%s';args.append(id)
                stmt+=' ORDER BY id DESC'
                if limit is not None:stmt+=' LIMIT %s';args.append(limit)
                q.execute(stmt,tuple(args));ids=q.fetchall()
        finally:c.close()
        for r in ids:yield self.get_tuple({'configurable':{'thread_id':thread,'checkpoint_ns':ns,'checkpoint_id':r[0]}})
    def delete_thread(self,thread_id):
        c=self._db()
        try:
            c.begin()
            with c.cursor() as q:
                q.execute('DELETE FROM mo_writes WHERE thread_id=%s',(thread_id,));q.execute('DELETE FROM mo_checkpoints WHERE thread_id=%s',(thread_id,))
            c.commit()
        except Exception:c.rollback();raise
        finally:c.close()
