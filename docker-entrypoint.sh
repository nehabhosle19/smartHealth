#!/bin/sh
# Apply database migrations, then start the server.
set -e
python -m alembic upgrade head

# Demo hosting without shell access (e.g. free Render): set SMARTHEALTH_DEMO_PASSWORD (and
# SMARTHEALTH_ENV=development) and the demo district is created / refreshed on every start.
if [ -n "$SMARTHEALTH_DEMO_PASSWORD" ] && [ "$SMARTHEALTH_ENV" != "production" ]; then
  python -m smarthealth.manage bootstrap-demo
fi
exec python -m uvicorn smarthealth.app:create_app --factory \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --no-server-header
