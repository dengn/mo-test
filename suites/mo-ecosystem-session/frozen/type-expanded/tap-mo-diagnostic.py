# Diagnostic adapter: skip startup logging of unsupported MySQL-only server variables.
# No metadata/type/binlog emulation, and no production or installed package edits.
import tap_mysql

def log_server_params(conn):
    from tap_mysql.connection import connect_with_backoff
    with connect_with_backoff(conn) as db:
        with db.cursor() as cur:
            cur.execute('SELECT VERSION()')
            tap_mysql.LOGGER.info('Diagnostic adapter: VERSION=%s; omitted MySQL-only parameter/status logging',cur.fetchone()[0])
tap_mysql.log_server_params=log_server_params
tap_mysql.main()
