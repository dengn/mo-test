### Summary

Spark 3.5.3's built-in JDBC writer defaults to `READ_UNCOMMITTED`. A standard Spark DataFrame write using MySQL Connector/J therefore fails against MatrixOne before inserting rows:

```text
java.sql.SQLException: not supported: transaction isolation level READ-UNCOMMITTED is not supported
  at com.mysql.cj.jdbc.ConnectionImpl.setTransactionIsolation(ConnectionImpl.java:2227)
  at org.apache.spark.sql.execution.datasources.jdbc.JdbcUtils$.savePartition(JdbcUtils.scala:721)
```

This issue tracks the **current Spark integration compatibility gap** and the supported configuration/documentation needed to make the integration work. It does not claim that MatrixOne currently promises dirty-read semantics, or that the fix for #26648 regressed.

### Minimal reproduction

Start MatrixOne and install `pyspark==3.5.3`; provide MySQL Connector/J 8.0.33.

```python
import os
from pyspark.sql import SparkSession

spark = (SparkSession.builder.master("local[1]")
         .appName("mo-spark-isolation-repro")
         .config("spark.jars", os.environ["MYSQL_CONNECTOR_JAR"])
         .getOrCreate())

# Use a dedicated test database.
url = os.environ["MO_JDBC_URL"]
props = {
    "driver": "com.mysql.cj.jdbc.Driver",
    "user": os.environ["MO_USER"],
    "password": os.environ["MO_PASSWORD"],
}
df = spark.createDataFrame([(1, 0.25), (2, 0.75)], "id long, value double")
df.write.jdbc(url, "spark_isolation_issue_repro", mode="append", properties=props)
# Actual: SparkException caused by unsupported READ-UNCOMMITTED.
```

Equivalent server-side reproduction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
-- ERROR 20105: not supported: transaction isolation level READ-UNCOMMITTED is not supported
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
-- Succeeds.
```

### Verified workaround

```python
props["isolationLevel"] = "READ_COMMITTED"
df.write.jdbc(url, "spark_isolation_issue_repro", mode="append", properties=props)
```

Fresh verification on 2026-10-11: the default write failed; the explicit RC write succeeded, and an independent SQL read returned `COUNT(*) = 2`, `SUM(value) = 1.0`.

In a larger JDBC source → Spark computation → JDBC sink → independent readback suite, all 10 default-config pipelines failed at this same isolation-setting point (1,000 affected group assertions, **not 1,000 independent defects**). With explicit `READ_COMMITTED`, the same 10 pipelines passed all 1,000 group assertions.

### Requested outcome

Provide a supported Spark JDBC integration path and a regression example that writes and reads back data using `isolationLevel=READ_COMMITTED`. Document this required option prominently in Spark integration instructions. If default Spark configuration compatibility is a product goal, define an explicit supported solution; do not silently map READ_UNCOMMITTED to another isolation level while claiming equivalent semantics.

### Related issues

- #4473: historical Spark insert discussion also mentions isolation-level limitations.
- #26648: fixed the standard SET SESSION isolation setter. Its regression verification explicitly rejects unsupported READ_UNCOMMITTED/SERIALIZABLE. This report is about the remaining default Spark integration behavior.

### Environment

- Executed mo-service build commit: `23d8f61252f3017dff218b530817a240206fd762` (binary build metadata; this differs from the checked-out source HEAD).
- `SELECT VERSION()`: `8.0.30-MatrixOne-v`
- Spark/PySpark 3.5.3; MySQL Connector/J 8.0.33; OpenJDK 21.0.12.1; Python 3.12
- Local dedicated synthetic-data instance, no production data.

