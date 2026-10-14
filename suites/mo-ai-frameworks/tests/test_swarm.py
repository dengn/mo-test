import pytest
from flows.swarm_workflow import sql_workflow,swarm_lifecycle
from adapters.framework_json import FileJsonSnapshots

@pytest.mark.project('swarm')
def test_swarm_sql_handoff_state_resume(db):sql_workflow(db.config)

@pytest.mark.project('swarm')
def test_swarm_native_lookup_file_reference(tmp_path):
    rows=[dict(id=1,tenant='a',content='alpha A 中文'),dict(id=2,tenant='b',content='beta B')]
    swarm_lifecycle(lambda tenant:[r for r in rows if r['tenant']==tenant],lambda tenant:FileJsonSnapshots(tmp_path,tenant))
