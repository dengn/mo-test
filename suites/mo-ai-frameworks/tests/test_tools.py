import pytest

@pytest.mark.project('smolagents')
def test_smolagents_agent_sql_observation(db,knowledge):
    from flows.tool_workflows import smolagents_loop
    assert 'actual ToolCallingAgent.run' in smolagents_loop(db.config)

@pytest.mark.project('dspy')
def test_dspy_react_sql_observation(db,knowledge):
    from flows.tool_workflows import dspy_loop
    assert 'actual ReAct/DummyLM' in dspy_loop(db.config)

@pytest.mark.project('litellm')
def test_litellm_sync_async_callback_reopen(db):
    from flows.tool_workflows import litellm_callbacks
    assert 'native completion/acompletion' in litellm_callbacks(db.config)
