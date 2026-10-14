import time
from typing import TypedDict
import pytest

@pytest.mark.project('langgraph')
def test_langgraph_interrupt_resume_checkpoint(db):
    from adapters.langgraph_checkpoint import MatrixOneSaver
    from langgraph.graph import StateGraph,START,END
    from langgraph.types import interrupt,Command
    class State(TypedDict):value:int
    def approve(state):return {'value':state['value']+int(interrupt('approve?'))}
    builder=StateGraph(State);builder.add_node('approve',approve);builder.add_edge(START,'approve');builder.add_edge('approve',END)
    saver=MatrixOneSaver(db.config);saver.setup();config={'configurable':{'thread_id':'a'}}
    graph=builder.compile(checkpointer=saver);assert '__interrupt__' in graph.invoke({'value':10},config)
    reopened_saver=MatrixOneSaver(db.config);reopened=builder.compile(checkpointer=reopened_saver)
    assert reopened.invoke(Command(resume=2),config)['value']==12
    assert reopened.get_state(config).values=={'value':12}
    assert reopened.get_state({'configurable':{'thread_id':'b'}}).values=={}
    assert len(list(reopened_saver.list(config)))>=3
    reopened_saver.delete_thread('a');assert reopened_saver.get_tuple(config) is None

@pytest.mark.project('agno')
def test_agno_legacy_upsert_session(db):
    from adapters.sqlalchemy_engine import matrixone_engine
    from agno.db.mysql import MySQLDb
    from agno.session import AgentSession
    engine=matrixone_engine(db.url())
    try:
        store=MySQLDb(db_engine=engine,db_schema=db.name,session_table='sessions')
        now=int(time.time());session=AgentSession(session_id='a',agent_id='agent',user_id='user',session_data={'counter':1},created_at=now,updated_at=now)
        assert store.upsert_session(session) is not None
        session.session_data={'counter':2};assert store.upsert_session(session) is not None
        reopened=MySQLDb(db_engine=engine,db_schema=db.name,session_table='sessions')
        assert reopened.get_session(session_id='a').session_data['counter']==2
    finally:engine.dispose()

@pytest.mark.project('memori')
def test_memori_native_schema_entity(db):
    import pymysql
    from memori import Memori
    memory=Memori(conn=lambda:pymysql.connect(**db.config),use_rust_core=False)
    memory.config.storage.build()
    assert memory.config.storage.driver.entity.create('regression-user') is not None
