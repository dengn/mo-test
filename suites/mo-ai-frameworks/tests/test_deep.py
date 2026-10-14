import pytest
from langgraph.checkpoint.memory import InMemorySaver
from flows.deepagents_workflow import filesystem_lifecycle,approval_lifecycle,sql_factory

@pytest.mark.project('deepagents')
def test_deepagents_filesystem_matrixone(db):filesystem_lifecycle(sql_factory(db.config))

@pytest.mark.project('deepagents')
def test_deepagents_approval_matrixone(db):approval_lifecycle(sql_factory(db.config))

@pytest.mark.project('deepagents')
def test_deepagents_filesystem_native():
    saver=InMemorySaver();filesystem_lifecycle(lambda:saver)

@pytest.mark.project('deepagents')
def test_deepagents_approval_native():
    saver=InMemorySaver();approval_lifecycle(lambda:saver)
