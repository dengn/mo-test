### Is there an existing issue for the same bug?

- [x] I searched existing open and closed issues for this reproducer.

### Branch Name

main

### Commit ID

2726fb419b3afa1db2686ae1b2aaca563d1ae214

### Other Environment Information

Linux x86_64, 4 CPU quota / 32 GiB memory, a single local mo-service running LOG/TN/CN with DISK-V2 file services. Built with Go 1.27.1. All data and credentials below are synthetic local test fixtures.

### Actual Behavior

The first CREATE PUBLICATION IF NOT EXISTS succeeds. Repeating the identical statement returns:

~~~text
ERROR 1062: Duplicate entry '(0,e2e_pub_idem)' for key '(account_id,pub_name)'
~~~

This also broke idempotent setup of the publish/subscribe test suite.

### Expected Behavior

IF NOT EXISTS should succeed as a no-op for an existing publication (optionally with a warning), retaining its definition. Ordinary CREATE without this clause may reject a duplicate.

### Steps to Reproduce

Connect as root in the sys account and execute ordinary SQL, not PREPARE:

~~~sql
CREATE DATABASE IF NOT EXISTS pub50;
CREATE TABLE IF NOT EXISTS pub50.visible
  (id BIGINT PRIMARY KEY, n BIGINT, label TEXT);
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
-- Unexpected ERROR 1062:
CREATE PUBLICATION IF NOT EXISTS e2e_pub_idem
  DATABASE pub50 TABLE visible ACCOUNT ALL;
DROP PUBLICATION IF EXISTS e2e_pub_idem;
~~~

### Additional information

The separate restriction on preparing CREATE PUBLICATION is not involved. The AST contains IfNotExists, but I did not find its use in the create path in pkg/frontend/publication_subscription.go. Product code was not modified.
