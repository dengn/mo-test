# Additional 100,000 cases: final execution record

Both extra packs have 50,000 distinct recorded result IDs matching their materialized case IDs. Total main instances: 600,000. Calibration, fault probes, timing controls and rechecks are separate.

- mo-corners-50000: 50,000 executed; raw statuses {'connection_or_runner_error': 620, 'pass': 34380, 'environment_or_unexpected_error': 515, 'pass_expected_rejection': 14485}.
- mo-enterprise-50000: 50,000 executed; raw statuses {'pass_expected_rejection': 15999, 'pass': 33999, 'execution_error': 2}.

The 1,135 unexpected TLS results consist of 620 positive-config handshake failures and 515 negative-case transport timeouts. They are not 1,135 distinct bugs. The SSLRequest/ClientHello timing issue has its own deterministic comparison.

Git4Data originally ran with 4 DDL workers, and its remaining cases resumed with 12 after preserving 46,805 results and cleaning only incomplete fixture tables. Client query timeouts retain their original records; serial rechecks are separate. This concurrency transition and any load-related failures must remain visible.

Task cron/resume eventually ran successfully within bounded polling; 1s timeouts rolled back. The subsecond value truncation is reported separately. Python UDF malformed return lengths/types produced clean SQL errors; stopping its service left MO available and calls recovered after reconnect backoff. Iceberg correctness used real files with the documented Nessie credentials adapter and local S3 fixture.

Fatal/panic log matches in the specified current and archived logs: 0. Memory events: low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0.

Submitted English issues:
- [[Bug]: Concurrent HNSW reindex and secondary-index DDL leave persistent inconsistent index metadata](https://github.com/matrixorigin/matrixone/issues/29927)
- [[Bug]: TLS handshake hangs when MySQL SSLRequest and ClientHello arrive together](https://github.com/matrixorigin/matrixone/issues/29928)
- [[Bug]: CREATE PUBLICATION IF NOT EXISTS returns a duplicate-key error for an existing publication](https://github.com/matrixorigin/matrixone/issues/29929)
- [[Bug]: Positive SQL task timeouts below one second silently disable the execution deadline](https://github.com/matrixorigin/matrixone/issues/29930)

This extends the earlier 500,000-case report; it does not turn documented compatibility differences, oracle corrections or clean boundary rejection into bugs. No other database engines or SaaS connectors were deployed in the mapped scenario packs.
