"""Add explicit MySQL VARCHAR lengths to the SDK's SQLAlchemy session schema.

The SDK currently declares unbounded String for session_id and fails on MySQL
before executing SQL. Keep all message, transaction and locking behavior native.
"""
from sqlalchemy import String
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
class BoundedSQLAlchemySession(SQLAlchemySession):
    def __init__(self,session_id,**kwargs):
        if len(session_id)>255:raise ValueError('session_id exceeds the configured VARCHAR(255) schema')
        super().__init__(session_id,**kwargs)
        self._sessions.c.session_id.type=String(255)
        self._messages.c.session_id.type=String(255)

class MatrixOneSQLAlchemySession(BoundedSQLAlchemySession):
    """Avoid the explicit child index while retaining the FK and ON DELETE CASCADE.

    Applies only to newly created tables. Existing indexed tables need an explicit
    migration. History lookup loses that secondary index, so benchmark it before
    production use. Native transactions and clear behavior remain unchanged.
    """
    def __init__(self,session_id,**kwargs):
        super().__init__(session_id,**kwargs)
        self._messages.indexes.clear()
