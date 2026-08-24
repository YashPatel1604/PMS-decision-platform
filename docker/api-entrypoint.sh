#!/bin/sh
set -eu
cd /app
alembic upgrade head
python -c "from pms_platform.auth.service import ensure_builtin_users; from pms_platform.db.base import get_session_factory; s=get_session_factory()();
try:
    ensure_builtin_users(s); s.commit()
finally:
    s.close()"
exec uvicorn pms_platform.api.main:app --host 0.0.0.0 --port 8000
