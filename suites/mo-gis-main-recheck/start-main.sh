#!/usr/bin/env bash
set -euo pipefail
source /workspace/matrixone-env.sh
cd /workspace/matrixone-gis-latest
if [ -f /workspace/mo-gis-main-recheck/server.pid ]; then
  gis_main_previous_pid=$(cat /workspace/mo-gis-main-recheck/server.pid)
  if kill -0 "$gis_main_previous_pid" 2>/dev/null; then
    echo 'Recorded process exists; verify its configuration before restarting.'
    exit 1
  fi
fi
nohup ./mo-service -launch /workspace/mo-gis-main-recheck/config/launch.toml > /workspace/mo-gis-main-recheck/server.log 2>&1 </dev/null &
echo $! > /workspace/mo-gis-main-recheck/server.pid
