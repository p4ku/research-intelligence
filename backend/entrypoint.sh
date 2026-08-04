#!/bin/sh
set -e

echo "🚀 [ENTRYPOINT] Running Django Database Migrations..."
python manage.py migrate --noinput

echo "📦 [ENTRYPOINT] Collecting Static Files..."
python manage.py collectstatic --noinput || true

if [ "$#" -gt 0 ]; then
    echo "⚡ [ENTRYPOINT] Executing custom command: $@"
    exec "$@"
else
    echo "🔥 [ENTRYPOINT] Starting Production WSGI Server (Gunicorn)..."
    exec gunicorn django_project.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-4} --timeout 120 --access-logfile -
fi
