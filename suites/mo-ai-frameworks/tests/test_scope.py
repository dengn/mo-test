import asyncio
import pytest
from flows.agentscope_workflow import workflow

@pytest.mark.project('agentscope')
def test_agentscope_toolkit_state_restore_continue(db):
    asyncio.run(workflow(db.config))
