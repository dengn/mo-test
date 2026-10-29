"""Scope SQLAlchemy's legacy VALUES upsert compiler to one MatrixOne engine."""
from sqlalchemy import create_engine
def matrixone_engine(url):
    engine=create_engine(url)
    with engine.connect():pass
    # MySQL >= 8.0.20 makes SQLAlchemy emit AS new; MatrixOne rejects that form.
    # This per-engine dialect switch retains bind parameters and VALUES semantics.
    engine.dialect._requires_alias_for_on_duplicate_key=False
    return engine
