package local.gis;

import java.util.HashMap;
import java.util.Map;
import org.geotools.jdbc.JDBCDataStore;
import org.geotools.jdbc.SQLDialect;
import org.geotools.data.mysql.MySQLDataStoreFactory;
import org.geotools.data.mysql.MySQLDialectBasic;

/** Application-only adapter for fixed-column-SRID MatrixOne geometry. */
public class MatrixOneDataStoreFactory extends MySQLDataStoreFactory {
    private static final Param MATRIXONE_TYPE = new Param(
        "dbtype", String.class, "Type", true, "matrixone");

    @Override
    public String getDisplayName() { return "MatrixOne GIS application test adapter"; }

    @Override
    public String getDescription() { return "MySQL JDBC with MatrixOne-native envelope SQL"; }

    @Override
    public boolean canProcess(Map<String, ?> params) {
        if (!"matrixone".equals(params.get("dbtype"))) return false;
        Map<String, Object> copy = new HashMap<>(params);
        copy.put("dbtype", "mysql");
        return super.canProcess(copy);
    }

    @Override
    protected void setupParameters(Map<String, Object> params) {
        super.setupParameters(params);
        params.put(DBTYPE.key, MATRIXONE_TYPE);
    }

    @Override
    protected SQLDialect createSQLDialect(JDBCDataStore store) {
        return new MatrixOneDialect(store);
    }

    public static class MatrixOneDialect extends MySQLDialectBasic {
        public MatrixOneDialect(JDBCDataStore store) { super(store, true); }

        @Override
        public void encodeGeometryEnvelope(String table, String column, StringBuffer sql) {
            // MO's ST_Envelope already preserves column SRID and supports its
            // geodetic path. No row-dependent SRID setter is needed.
            sql.append("ST_AsWKB(ST_Envelope(");
            encodeColumnName(null, column, sql);
            sql.append("))");
        }
    }
}
