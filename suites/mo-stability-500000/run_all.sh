#!/usr/bin/env bash
set -euo pipefail
export MO_SUITE_DATABASE="suite500_$(date +%s)"
mo_python=/workspace/toolchains/python/bin/python
mo_args=(--workers 24)
if ! env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock inspect --format '{{.State.Running}}' mo-case-reference-mysql | rg -q true; then
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock start mo-case-reference-mysql
fi
"$mo_python" /workspace/mo-cases-50000/runner.py --bootstrap
for pack in mo-cases-50000 mo-chaos-50000 mo-crossdb-100000 mo-etl-100000 mo-gap-200000; do
  if [[ "$pack" == mo-crossdb-100000 || "$pack" == mo-etl-100000 ]]; then
    "$mo_python" "/workspace/$pack/runner.py" --bootstrap
  fi
  "$mo_python" "/workspace/$pack/runner.py" "${mo_args[@]}" --output "replay-${MO_SUITE_DATABASE}.jsonl"
done
