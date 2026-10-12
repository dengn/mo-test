### Is there an existing issue for the same bug?

- [x] I searched existing open and closed issues for this reproducer.

### Branch Name

main

### Commit ID

2726fb419b3afa1db2686ae1b2aaca563d1ae214

### Other Environment Information

Linux x86_64, 4 CPU quota / 32 GiB memory, a single local mo-service running LOG/TN/CN with DISK-V2 file services. Built with Go 1.27.1. All data and credentials below are synthetic local test fixtures.

### Actual Behavior

CREATE TASK accepts a positive subsecond timeout, then stores it as zero and disables the execution deadline:

|Requested timeout|Stored timeout_seconds|Result|Rows committed|
|---|---:|---|---:|
|100ms|0|SUCCESS; about 2.37 seconds client wall time|1|
|1s|1|TIMEOUT; about 1.09 seconds client wall time|0|
|3s|3|SUCCESS|1|

All bodies use INSERT ... SELECT SLEEP(2). Ordinary task timeouts are not generally broken: the 1s control correctly timed out and rolled back.

The 1s error was ERROR 20101: context deadline exceeded / internal executor exec.

### Expected Behavior

A positive timeout must not silently turn into unlimited execution. If subsecond precision is unsupported, reject it clearly or retain a conservative nonzero bound. This reports silent disabling, rather than requiring nanosecond precision.

### Steps to Reproduce

~~~sql
CREATE DATABASE IF NOT EXISTS task_timeout_repro;
USE task_timeout_repro;
CREATE TABLE sink(kind INT, v INT);

CREATE TASK tt_100ms TIMEOUT '100ms'
  AS BEGIN INSERT INTO sink SELECT 0, SLEEP(2); END;
EXECUTE TASK tt_100ms;
SELECT COUNT(*) FROM sink WHERE kind=0; -- actual 1
SELECT timeout_seconds FROM mo_task.sql_task
  WHERE task_name='tt_100ms'; -- actual 0
SELECT status FROM mo_task.sql_task_run
  WHERE task_name='tt_100ms' ORDER BY run_id DESC LIMIT 1; -- SUCCESS

CREATE TASK tt_1s TIMEOUT '1s'
  AS BEGIN INSERT INTO sink SELECT 1, SLEEP(2); END;
EXECUTE TASK tt_1s; -- expected/actual deadline error
SELECT COUNT(*) FROM sink WHERE kind=1; -- actual 0
SELECT status FROM mo_task.sql_task_run
  WHERE task_name='tt_1s' ORDER BY run_id DESC LIMIT 1; -- TIMEOUT

CREATE TASK tt_3s TIMEOUT '3s'
  AS BEGIN INSERT INTO sink SELECT 2, SLEEP(2); END;
EXECUTE TASK tt_3s;
SELECT COUNT(*) FROM sink WHERE kind=2; -- actual 1

DROP TASK tt_100ms;
DROP TASK tt_1s;
DROP TASK tt_3s;
DROP TABLE sink;
DROP DATABASE task_timeout_repro;
~~~

### Additional information

ParseSQLTaskTimeout in pkg/taskservice/sql_task_utils.go accepts the duration and returns int(d / time.Second), so 100ms becomes 0. sql_task_executor.go only sets a deadline when TimeoutSeconds > 0.

The existing SQL regression uses 1s and expects TIMEOUT; that control passed here. Supporting or rejecting subsecond inputs is a policy choice, but silently accepting and disabling the bound is the reported behavior.
