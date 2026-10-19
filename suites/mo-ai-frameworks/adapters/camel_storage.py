"""CAMEL append-only chat history storage, scoped to one conversation."""
import json
import pymysql
from camel.storages.key_value_storages import BaseKeyValueStorage
from camel.storages.key_value_storages.json import CamelJSONEncoder

class MatrixOneCamelStorage(BaseKeyValueStorage):
    def __init__(self, connection_config, namespace):
        if not isinstance(namespace, str) or not namespace or len(namespace) > 128:
            raise ValueError('namespace must contain 1–128 characters')
        self.config = dict(connection_config)
        self.namespace = namespace
        self._query('CREATE TABLE IF NOT EXISTS camel_history(id BIGINT AUTO_INCREMENT PRIMARY KEY, namespace VARCHAR(128), payload JSON, INDEX(namespace))')

    def _query(self, sql, args=None):
        with pymysql.connect(**self.config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.fetchall()

    def save(self, records):
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            raise TypeError('records must be a list of dictionaries')
        # Serialize the entire batch before starting a transaction.
        values = [(self.namespace, json.dumps(r, cls=CamelJSONEncoder, ensure_ascii=False, allow_nan=False)) for r in records]
        if not values:
            return
        with pymysql.connect(**self.config) as connection:
            connection.begin()
            try:
                with connection.cursor() as cursor:
                    cursor.executemany('INSERT INTO camel_history(namespace,payload) VALUES(%s,%s)', values)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _decode(value):
        if '__enum__' in value:
            name, member = value['__enum__'].split('.')
            return getattr(CamelJSONEncoder.CAMEL_ENUMS[name], member)
        return value

    def load(self):
        return [json.loads(r[0], object_hook=self._decode) for r in self._query('SELECT payload FROM camel_history WHERE namespace=%s ORDER BY id', (self.namespace,))]

    def clear(self):
        self._query('DELETE FROM camel_history WHERE namespace=%s', (self.namespace,))
