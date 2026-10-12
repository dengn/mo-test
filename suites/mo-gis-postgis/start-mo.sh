#!/usr/bin/env bash
set -euo pipefail
source /workspace/matrixone-env.sh
cd /workspace/matrixone-gis-latest
if [ -f /workspace/mo-gis-postgis/server.pid ]; then
  gis_previous_pid=$(cat /workspace/mo-gis-postgis/server.pid)
  if [ "$(ps -p "$gis_previous_pid" -o comm= 2>/dev/null || true)" = mo-service ] && [[ "$(ps -p "$gis_previous_pid" -o stat= 2>/dev/null || true)" != Z* ]]; then
    echo 'GIS test instance already running'
    exit 0
  fi
fi
nohup ./mo-service -launch /workspace/mo-gis-postgis/config/launch.toml > /workspace/mo-gis-postgis/server.log 2>&1 </dev/null &
echo $! > /workspace/mo-gis-postgis/server.pid
