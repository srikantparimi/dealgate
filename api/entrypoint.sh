#!/usr/bin/env sh
# DealGate API container entrypoint.
#
# Two modes, one image:
#   RUN_MIGRATIONS=true   -> apply alembic and exit (ECS one-off task).
#   otherwise             -> serve uvicorn on :8000 behind the ALB.
set -eu

cd /app

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] running alembic upgrade head"
    exec alembic upgrade head
fi

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips='*'
