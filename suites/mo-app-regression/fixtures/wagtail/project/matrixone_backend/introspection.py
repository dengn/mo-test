"""Read constraints from SHOW CREATE TABLE, including MatrixOne foreign keys."""
import re
from mysql.connector.django.introspection import DatabaseIntrospection as MySQLIntrospection

class DatabaseIntrospection(MySQLIntrospection):
    def get_constraints(self, cursor, table_name):
        cursor.execute('SHOW CREATE TABLE ' + self.connection.ops.quote_name(table_name))
        definition = cursor.fetchone()[1]
        result = {}
        for line in definition.splitlines():
            line = line.strip().rstrip(',')
            primary = re.match(r'PRIMARY KEY \((.*?)\)', line)
            index = re.match(r'(UNIQUE )?(?:KEY|INDEX) `([^`]+)` \((.*?)\)', line)
            foreign = re.match(r'CONSTRAINT `([^`]+)` FOREIGN KEY \((.*?)\) REFERENCES `([^`]+)` \((.*?)\)', line)
            if primary:
                name, columns, unique, fk = 'PRIMARY', primary[1], True, None
            elif index:
                name, columns, unique, fk = index[2], index[3], bool(index[1]), None
            elif foreign:
                name, columns, unique = foreign[1], foreign[2], False
                fk = (foreign[3], re.findall(r'`([^`]+)`', foreign[4])[0])
            else:
                continue
            names = re.findall(r'`([^`]+)`', columns)
            result[name] = {'columns': names, 'primary_key': bool(primary), 'unique': unique,
                            'foreign_key': fk, 'check': False, 'index': fk is None,
                            'orders': ['ASC'] * len(names), 'type': 'idx'}
        return result
