#!/bin/sh
set -eu
cd /app
alembic upgrade head
exec uvicorn pms_platform.api.main:app --host 0.0.0.0 --port 8000
