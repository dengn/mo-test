from . import lookups
"""MatrixOne schema adapter. Preserve Python JSON defaults with explicit backfill."""
from mysql.connector.django.base import DatabaseWrapper as ConnectorDatabaseWrapper
from django.db.models.fields import NOT_PROVIDED


class MatrixOneSchemaEditor(ConnectorDatabaseWrapper.SchemaEditorClass):
    # MatrixOne rejects ADD COLUMN + ADD FOREIGN KEY in one ALTER; Django's
    # deferred path issues a separate ALTER and preserves the actual constraint.
    sql_create_column_inline_fk = None

    def add_constraint(self, model, constraint):
        if constraint.name == "permission_or_permission_type_not_null":
            table = self.quote_name(model._meta.db_table)
            # The preceding migration backfills every permission. A stricter
            # NOT NULL can enforce the final schema throughout fresh install.
            with self.connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE permission_id IS NULL")
                if cursor.fetchone()[0]:
                    raise RuntimeError("Permission backfill must finish before adding NOT NULL")
            self.execute(f"ALTER TABLE {table} MODIFY COLUMN `permission_id` integer NOT NULL")
            return
        return super().add_constraint(model, constraint)

    def remove_constraint(self, model, constraint):
        if constraint.name == "permission_or_permission_type_not_null":
            # The stronger NOT NULL remains; the following migration declares
            # permission non-nullable and removes the obsolete permission type.
            return
        return super().remove_constraint(model, constraint)

    def execute(self, sql, params=()):
        import sys
        import re
        match = re.match(r"CREATE (UNIQUE )?INDEX `([^`]+)` ON `([^`]+)` \((.*?)\)", str(sql))
        if match:
            with self.connection.cursor() as cursor:
                constraints = self.connection.introspection.get_constraints(cursor, match[3])
            existing = constraints.get(match[2])
            if existing:
                columns = re.findall(r"`([^`]+)`", match[4])
                if existing["columns"] != columns or existing["unique"] != bool(match[1]):
                    raise RuntimeError("Existing index differs from requested definition: " + match[2])
                return
        print("MATRIXONE_SCHEMA_SQL:", str(sql), file=sys.stderr)
        return super().execute(sql, params)

    def skip_default(self, field):
        return field.get_internal_type() == "JSONField" or super().skip_default(field)

    def remove_field(self, model, field):
        # MatrixOne's DROP COLUMN rebuild fails with an unrelated self-FK.
        # Detach only that self-FK, perform the real removal, then restore it.
        import re
        table = model._meta.db_table
        quoted = self.quote_name(table)
        with self.connection.cursor() as cursor:
            cursor.execute(f"SHOW CREATE TABLE {quoted}")
            definition = cursor.fetchone()[1]
        constraints = []
        for line in definition.splitlines():
            clause = line.strip().rstrip(",")
            match = re.match(r"CONSTRAINT `([^`]+)` FOREIGN KEY \((.*?)\) REFERENCES `([^`]+)` \((.*?)\)", clause)
            if match and match[3] == table and field.column not in re.findall(r"`([^`]+)`", match[2] + match[4]):
                constraints.append((match[1], clause))
        for name, _ in constraints:
            self.execute(f"ALTER TABLE {quoted} DROP FOREIGN KEY {self.quote_name(name)}")
        try:
            super().remove_field(model, field)
        finally:
            for _, clause in constraints:
                self.execute(f"ALTER TABLE {quoted} ADD {clause}")

    def add_field(self, model, field):
        if field.get_internal_type() != "JSONField":
            return super().add_field(model, field)
        # Temporary SQL defaults on JSON are rejected by MatrixOne. Add nullable,
        # backfill the callable default, then restore the requested nullability.
        nullable = field.clone()
        nullable.set_attributes_from_name(field.name)
        nullable.null = True
        nullable.default = NOT_PROVIDED
        super().add_field(model, nullable)
        table = self.quote_name(model._meta.db_table)
        column = self.quote_name(field.column)
        if field.has_default():
            self.execute(f"UPDATE {table} SET {column} = %s WHERE {column} IS NULL",
                         [self.effective_default(field)])
        if not field.null:
            self.execute(f"ALTER TABLE {table} MODIFY COLUMN {column} JSON NOT NULL")


from .introspection import DatabaseIntrospection
from .features import DatabaseFeatures

class DatabaseWrapper(ConnectorDatabaseWrapper):
    introspection_class = DatabaseIntrospection
    features_class = DatabaseFeatures
    # Connector/Python's callable display_name is incompatible with Django 6.1.
    display_name = "MatrixOne via MySQL Connector"
    SchemaEditorClass = MatrixOneSchemaEditor


def trace_query_error(execute, sql, params, many, context):
    try:
        return execute(sql, params, many, context)
    except Exception as exc:
        import sys
        import os
        import json
        journal = os.getenv('MO_NATIVE_SQL_ERROR_FILE')
        if journal:
            # Private diagnostics only; never upload arbitrary parameters/logs.
            with os.fdopen(os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), 'a') as stream:
                stream.write(json.dumps({'sql_template': sql, 'parameters': params,
                                         'error_type': type(exc).__name__}, default=str, ensure_ascii=False) + '\n')
        print("MATRIXONE_QUERY_ERROR:", type(exc).__name__, str(exc), "SQL:", sql, file=sys.stderr)
        raise

_original_init = DatabaseWrapper.__init__
def _traced_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.execute_wrappers.append(trace_query_error)
DatabaseWrapper.__init__ = _traced_init
