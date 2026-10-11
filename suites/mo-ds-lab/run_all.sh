#!/usr/bin/env bash
set -euo pipefail
cd /workspace/mo-ds-lab
TEST_PYTHON=${TEST_PYTHON:-/workspace/mo-ds-venv/bin/python}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 SPARK_LOCAL_IP=127.0.0.1
# Preserve the canonical default Spark configuration before the separate workaround.
unset SPARK_JDBC_ISOLATION
"$TEST_PYTHON" run_core.py > core.log 2>&1
"$TEST_PYTHON" run_connectors.py spark > spark.log 2>&1
"$TEST_PYTHON" run_connectors.py flink > flink.log 2>&1
SPARK_JDBC_ISOLATION=READ_COMMITTED "$TEST_PYTHON" run_connectors.py spark \
  --out results/spark-read-committed > spark-read-committed.log 2>&1
"$TEST_PYTHON" run_supplemental.py > supplemental.log 2>&1
"$TEST_PYTHON" summarize.py
