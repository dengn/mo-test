# Explicit diagnostic adapter: initialize the actual tap connection as utf8mb4.
# On MatrixOne, omit MySQL-only startup diagnostic logging (not CDC emulation).
import sys,tap_mysql
from tap_mysql.connection import MySQLConnection,connect_with_backoff
original_connect=MySQLConnection.connect
def connect_utf8(self,*args,**kwargs):
    original_connect(self,*args,**kwargs)
    self.set_charset('utf8mb4')
MySQLConnection.connect=connect_utf8
if '--matrixone-diagnostic' in sys.argv:
    sys.argv.remove('--matrixone-diagnostic')
    def log_server_params(conn):
        with connect_with_backoff(conn) as db,db.cursor() as c:
            c.execute('SELECT VERSION()')
            tap_mysql.LOGGER.info('Diagnostic adapter: VERSION=%s; omitted MySQL-only status logging',c.fetchone()[0])
    tap_mysql.log_server_params=log_server_params
tap_mysql.main()
