#!/usr/bin/env bash
set -euo pipefail
source /workspace/matrixone-env.sh
cd /workspace/matrixone-latest
if [ -f /workspace/mo-stress/server.pid ]; then
  previous_pid=$(cat /workspace/mo-stress/server.pid)
  if [ "$(ps -p "$previous_pid" -o comm= 2>/dev/null || true)" = mo-service ] && [[ "$(ps -p "$previous_pid" -o stat= 2>/dev/null || true)" != Z* ]]; then
    echo 'Stress instance already running'
    exit 0
  fi
fi
nohup ./mo-service -launch /workspace/mo-stress/config/launch.toml > /workspace/mo-stress/server.log 2>&1 &
echo $! > /workspace/mo-stress/server.pid
