# Submitted issues

These reports were filed in English against matrixorigin/matrixone. Each report includes the tested commit, observed results and a reproducer.

- [[Bug]: Concurrent HNSW reindex and secondary-index DDL leave persistent inconsistent index metadata](https://github.com/matrixorigin/matrixone/issues/29927)
- [[Bug]: TLS handshake hangs when MySQL SSLRequest and ClientHello arrive together](https://github.com/matrixorigin/matrixone/issues/29928)
- [[Bug]: CREATE PUBLICATION IF NOT EXISTS returns a duplicate-key error for an existing publication](https://github.com/matrixorigin/matrixone/issues/29929)
- [[Bug]: Positive SQL task timeouts below one second silently disable the execution deadline](https://github.com/matrixorigin/matrixone/issues/29930)
- [[Bug]: CREATE TABLE with excessive columns panics in TN Schema.Finalize and terminates mo-service](https://github.com/matrixorigin/matrixone/issues/30011) — [follow-up column boundary evidence](suites/mo-column-boundary/README.md), including the smaller 65,533-column reproduction and reserved-column read failures.
