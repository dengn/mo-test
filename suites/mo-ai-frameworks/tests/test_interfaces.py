import pytest
from flows import langextract_workflow,ag_ui_workflow

@pytest.mark.project('langextract')
def test_langextract_extract_align_matrixone(db):langextract_workflow.sql_workflow(db.config)

@pytest.mark.project('langextract')
def test_langextract_native_jsonl(tmp_path):langextract_workflow.extraction_lifecycle(lambda tenant:langextract_workflow.NativeJsonlDocuments(tmp_path,tenant))

@pytest.mark.project('ag-ui')
def test_ag_ui_protocol_journal_matrixone(db):ag_ui_workflow.sql_workflow(db.config)

@pytest.mark.project('ag-ui')
def test_ag_ui_native_SSE_reference(tmp_path):ag_ui_workflow.event_lifecycle(lambda tenant:ag_ui_workflow.NativeEncodedJournal(tmp_path,tenant))
