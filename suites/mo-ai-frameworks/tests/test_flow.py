import os
from pathlib import Path
import pytest
os.environ['OTEL_SDK_DISABLED']='true'
os.environ['CREWAI_TELEMETRY_DISABLED']='true'
os.environ['CREWAI_DISABLE_TELEMETRY']='true'
os.environ['CREWAI_STORAGE_DIR']=str(Path(os.environ['MO_RUNTIME_DIR'])/'crewai')
# Test-only relocation of the SDK-generated fixture key; preserve HOME.
from crewai_core.token_manager import TokenManager
def credential_directory():
    path=Path(os.environ['MO_RUNTIME_DIR'])/'crewai/credentials'
    path.mkdir(parents=True,exist_ok=True);path.chmod(0o700)
    return path
TokenManager._get_secure_storage_path=staticmethod(credential_directory)
from crewai.flow.persistence import SQLiteFlowPersistence
from adapters.crewai_persistence import MatrixOneFlowPersistence
from flows.crewai_workflow import lifecycle

@pytest.mark.project('crewai')
def test_crewai_matrixone_flow_restore_continue(db):
    lifecycle(MatrixOneFlowPersistence(db.config),lambda:MatrixOneFlowPersistence(db.config))

@pytest.mark.project('crewai')
def test_crewai_native_sqlite_reference(tmp_path):
    path=str(tmp_path/'flow.sqlite')
    lifecycle(SQLiteFlowPersistence(db_path=path),lambda:SQLiteFlowPersistence(db_path=path))
