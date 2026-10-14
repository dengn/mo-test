"""Avoid MatrixOne's IN + LIKE path index planner error for tree paths."""
from django.db.models import CharField
from django.db.models.lookups import StartsWith

@CharField.register_lookup
class MatrixOnePathStartsWith(StartsWith):
    def as_mysql(self, compiler, connection):
        field = self.lhs.output_field
        prefix = self.rhs
        if field.name == 'path' and isinstance(prefix, str) and prefix and all(c in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in prefix):
            lhs, params = self.process_lhs(compiler, connection)
            return f'LEFT({lhs}, %s) = %s', [*params, len(prefix), prefix]
        return super().as_sql(compiler, connection)
