"""MatrixOne-specific SQLAlchemy identifier and reflection compatibility."""
from sqlalchemy.dialects.mysql.base import MySQLIdentifierPreparer, MySQLDialect
from sqlalchemy import Boolean, LargeBinary
from sqlalchemy.dialects.mysql import BLOB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import AddConstraint
import pymysql
MySQLIdentifierPreparer.reserved_words = MySQLIdentifierPreparer.reserved_words | {'config'}
MySQLDialect.ischema_names = dict(MySQLDialect.ischema_names, bool=Boolean)
# Superset's MySQL schema-switching path selects the MySQLdb dialect.
# PyMySQL supplies its supported DB-API shim without system mysqlclient headers.
pymysql.install_as_MySQLdb()

@compiles(BLOB, 'mysql')
@compiles(LargeBinary, 'mysql')
def compile_matrixone_blob(type_, compiler, **kw):
    """Use the MySQL large binary spelling without an unsupported length."""
    if type_.length and type_.length > 65535:
        return 'LONGBLOB'
    return compiler.visit_BLOB(BLOB(), **kw)

@compiles(AddConstraint, 'mysql')
def compile_matrixone_constraint(element, compiler, **kw):
    constraint = element.element
    if (constraint.name == 'ck_chart_datasource'
            and constraint.table.name == 'slices'
            and str(constraint.sqltext) == "datasource_type in ('table')"):
        # A single-value nullable enum rejects the same non-null invalid values.
        # MatrixOne rejects ALTER ADD CHECK; it enforces ENUM on both DDL and DML.
        return "ALTER TABLE slices MODIFY datasource_type ENUM('table') NULL"
    return compiler.visit_add_constraint(element, **kw)
