#!/bin/sh
set -eu
cd /app
# Local Docker defaults to migrate-on-start. Production Railway sets RUN_MIGRATIONS_ON_START=0
# and runs docker/migrate-entrypoint.sh (or `pms-platform migrate`) as a one-shot release task.
if [ "${RUN_MIGRATIONS_ON_START:-1}" = "1" ]; then
  pms-platform migrate
fi
exec uvicorn pms_platform.api.main:app --host 0.0.0.0 --port 8000
