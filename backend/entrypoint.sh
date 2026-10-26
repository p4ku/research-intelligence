#!/bin/sh
set -e

# Wait for PostgreSQL to become available when DB_HOST is set
if [ -n "$DB_HOST" ]; then
    echo "⏳ [ENTRYPOINT] Waiting for database at ${DB_HOST}:${DB_PORT:-5432}..."
    python - <<'EOF'
import os
import sys
import time
import socket
import psycopg2

db_host = os.environ.get("DB_HOST")
if db_host:
    db_name = os.environ.get("DB_NAME", "research_intelligence")
    db_user = os.environ.get("DB_USER", "postgres")
    db_password = os.environ.get("DB_PASSWORD", "development_password")
    db_port = os.environ.get("DB_PORT", "5432")
    db_sslmode = os.environ.get("DB_SSLMODE", "prefer")
    connect_timeout = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))

    print(f"🔍 [ENTRYPOINT] DB Target Config: host={db_host}, port={db_port}, db={db_name}, user={db_user}, sslmode={db_sslmode}, pass_len={len(db_password)}")
    try:
        ip = socket.gethostbyname(db_host)
        print(f"🌐 [ENTRYPOINT] Resolved {db_host} -> {ip}")
    except Exception as dns_err:
        print(f"⚠️ [ENTRYPOINT] DNS resolution failed for {db_host}: {dns_err}")

    max_retries = 30
    for i in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=db_host,
                port=db_port,
                sslmode=db_sslmode,
                connect_timeout=connect_timeout
            )
            conn.close()
            print(f"✅ [ENTRYPOINT] Connected to PostgreSQL successfully at {db_host}:{db_port}/{db_name} (user: {db_user})")
            sys.exit(0)
        except Exception as e:
            print(f"⏳ [ENTRYPOINT] Waiting for PostgreSQL (attempt {i}/{max_retries}) [user={db_user} db={db_name} {db_host}:{db_port} sslmode={db_sslmode}]: {e}")
            time.sleep(2)

    print(f"❌ [ENTRYPOINT] Could not connect to PostgreSQL at {db_host}:{db_port}/{db_name} (user: {db_user}) within timeout.")
    sys.exit(1)
EOF
fi

# Ensure Object Storage (S3 / MinIO) bucket exists if configured
if [ "$STORAGE_BACKEND" = "s3" ] || [ "$STORAGE_BACKEND" = "minio" ] || [ -n "$AWS_S3_ENDPOINT_URL" ] || [ -n "$MINIO_ENDPOINT" ]; then
    echo "🪣 [ENTRYPOINT] Ensuring S3 / MinIO storage bucket exists..."
    python - <<'EOF'
import os
import sys

bucket_name = os.environ.get("AWS_STORAGE_BUCKET_NAME", "schwarz-research-intelligence")
endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL", os.environ.get("MINIO_ENDPOINT"))
access_key = os.environ.get("AWS_ACCESS_KEY_ID", os.environ.get("MINIO_ACCESS_KEY", "minio_dev_user"))
secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", os.environ.get("MINIO_SECRET_KEY", "minio_dev_password"))
region = os.environ.get("AWS_S3_REGION_NAME", "eu-central-1")

if endpoint_url and not endpoint_url.startswith("http"):
    use_ssl = os.environ.get("AWS_S3_USE_SSL", os.environ.get("MINIO_SECURE", "False")).lower() in ["true", "1", "yes"]
    protocol = "https" if use_ssl else "http"
    endpoint_url = f"{protocol}://{endpoint_url}"

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    boto_config = Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 2})
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=boto_config,
    )
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"✅ [ENTRYPOINT] S3/MinIO bucket '{bucket_name}' verified.")
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in ["404", "NoSuchBucket", "NotFound"]:
            print(f"🪣 [ENTRYPOINT] Bucket '{bucket_name}' not found. Auto-creating...")
            try:
                s3.create_bucket(Bucket=bucket_name)
            except Exception:
                if region and region != "us-east-1":
                    s3.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": region},
                    )
                else:
                    raise
            print(f"✅ [ENTRYPOINT] S3/MinIO bucket '{bucket_name}' created successfully.")
        else:
            print(f"⚠️ [ENTRYPOINT] S3/MinIO bucket check warning: {e}")
except Exception as e:
    print(f"⚠️ [ENTRYPOINT] Could not verify/create S3/MinIO bucket '{bucket_name}': {e}")
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
    exec gunicorn django_project.wsgi:application \
        --bind 0.0.0.0:${PORT:-8000} \
        --workers ${GUNICORN_WORKERS:-2} \
        --threads ${GUNICORN_THREADS:-4} \
        --worker-class gthread \
        --worker-tmp-dir /dev/shm \
        --keep-alive 65 \
        --timeout 300 \
        --access-logfile -
fi


