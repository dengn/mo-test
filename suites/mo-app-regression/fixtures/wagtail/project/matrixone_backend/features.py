from mysql.connector.django.features import DatabaseFeatures as MySQLFeatures

class DatabaseFeatures(MySQLFeatures):
    # MatrixOne requires selected non-aggregate columns in GROUP BY even when
    # a table's primary key is grouped; let Django emit the full grouping.
    allows_group_by_selected_pks = False
    # MatrixOne has transactions but no SAVEPOINT implementation.
    uses_savepoints = False
