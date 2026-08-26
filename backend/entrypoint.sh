#!/bin/sh
set -e

# Wait for PostgreSQL to become available when DB_HOST is set
if [ -n "$DB_HOST" ]; then
    echo "⏳ [ENTRYPOINT] Waiting for database at ${DB_HOST}:${DB_PORT:-5432}..."
    python - <<'EOF'
import os
import sys
import time
import psycopg2

db_host = os.environ.get("DB_HOST")
if db_host:
    db_name = os.environ.get("DB_NAME", "research_intelligence")
    db_user = os.environ.get("DB_USER", "postgres")
    db_password = os.environ.get("DB_PASSWORD", "development_password")
    db_port = os.environ.get("DB_PORT", "5432")

    max_retries = 30
    for i in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=db_host,
                port=db_port,
                connect_timeout=3
            )
            conn.close()
            print(f"✅ [ENTRYPOINT] Connected to PostgreSQL at {db_host}:{db_port}/{db_name}")
            sys.exit(0)
        except Exception as e:
            print(f"⏳ [ENTRYPOINT] Waiting for PostgreSQL (attempt {i}/{max_retries}): {e}")
            time.sleep(2)

    print("❌ [ENTRYPOINT] Could not connect to PostgreSQL within timeout.")
    sys.exit(1)
EOF
fi

if [ "$#" -gt 0 ]; then
    echo "⚡ [ENTRYPOINT] Executing custom command: $@"
    exec "$@"
else
    echo "🚀 [ENTRYPOINT] Running Django Database Migrations..."
    python manage.py migrate --noinput

    echo "📦 [ENTRYPOINT] Collecting Static Files..."
    python manage.py collectstatic --noinput || true

    echo "🔥 [ENTRYPOINT] Starting Production WSGI Server (Gunicorn on port ${PORT:-8000})..."
    exec gunicorn django_project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-4} --timeout 120 --access-logfile -
fi

