"""
Django Settings for Schwarz Research Intelligence Platform.

Systematic Literature Review (SLR) & Deep-Tech Competitive Intelligence Engine.
Modular Architecture:
  - `research_intelligence`: Core data models, pipeline state machine, Celery tasks (Steps 1-6).
  - `api`: Django REST Framework (DRF) endpoints, serializers, OpenAPI 3.0 Spectacular schema.
  - `chat`: Multi-turn Paper Chat session engine, Gemini Context Caching, and streaming.
  - `mcp`: Model Context Protocol (FastMCP) server, SSE endpoints, and AI tool catalog.

Database: PostgreSQL (Production) / SQLite In-Memory (Test Runner).
Task Queue: Celery + Redis.
Notifications: Mailgun Transactional API.
"""


from pathlib import Path
import os
import sys
import json

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present (checking both workspace root and backend root)
try:
    import dotenv
    dotenv.load_dotenv(BASE_DIR.parent / '.env')
    dotenv.load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

DEFAULT_INSECURE_SECRET = 'django-insecure-qrc9z6($69d3iz=jsd35l6ve+k%ljhifk4o-ph$%4-v!6ftr-x'
SECRET_KEY = os.environ.get('SECRET_KEY', DEFAULT_INSECURE_SECRET)

is_testing = 'test' in sys.argv or 'pytest' in sys.modules or bool(os.environ.get('DJANGO_TESTING'))

DEBUG = os.environ.get('DEBUG', 'False').lower() in ['true', '1', 'yes']
if is_testing:
    DEBUG = False

if not DEBUG and not is_testing:
    from django.core.exceptions import ImproperlyConfigured
    if not SECRET_KEY or SECRET_KEY == DEFAULT_INSECURE_SECRET:
        raise ImproperlyConfigured(
            "SECURITY ERROR: Running in production (DEBUG=False) with unset or default insecure SECRET_KEY. "
            "Please configure SECRET_KEY in your environment."
        )

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]
if is_testing:
    ALLOWED_HOSTS = ['*']
elif not DEBUG:
    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "SECURITY ERROR: In production (DEBUG=False), ALLOWED_HOSTS cannot be empty or contain wildcard '*'. "
            "Please configure explicit hostnames in your ALLOWED_HOSTS environment variable."
        )
elif not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
if not CSRF_TRUSTED_ORIGINS:
    for host in ALLOWED_HOSTS:
        if host != '*':
            CSRF_TRUSTED_ORIGINS.append(f"https://{host}")
            CSRF_TRUSTED_ORIGINS.append(f"http://{host}")

# Reverse proxy / Cloud Foundry SSL header forwarding
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Security Hardening Settings
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True



# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Third-party Applications
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    
    # Internal Modular Applications
    'api',
    'research_intelligence',
    'chat',
    'mcp_server',
    'observability',
]



MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.UserActionAuditMiddleware',
]

ROOT_URLCONF = 'django_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'django_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases


# Boot-time Google credentials diagnostics
if not is_testing:
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    
    if not sa_json:
        sys.stderr.write(
            "\n"
            "⚠️ [BOOT WARNING] GOOGLE_SERVICE_ACCOUNT_JSON is not configured in the environment!\n"
            "⚠️ [BOOT WARNING] Google GenAI / Vertex AI models will fail to authenticate.\n"
            "\n"
        )
    else:
        try:
            import json
            json.loads(sa_json)
        except Exception as e:
            sys.stderr.write(
                f"\n"
                f"⚠️ [BOOT WARNING] GOOGLE_SERVICE_ACCOUNT_JSON is set but has invalid JSON syntax: {str(e)}\n"
                f"⚠️ [BOOT WARNING] Google GenAI / Vertex AI models will fail to authenticate.\n"
                f"\n"
            )

db_host = os.environ.get('DB_HOST')
if db_host and not is_testing:
    db_sslmode = os.environ.get('DB_SSLMODE')
    db_options = {}
    if db_sslmode:
        db_options['sslmode'] = db_sslmode

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'research_intelligence'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'development_password'),
            'HOST': db_host,
            'PORT': os.environ.get('DB_PORT', '5432'),
            'OPTIONS': db_options,
            'TEST': {
                'NAME': ':memory:',
            }
        }
    }

else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'TEST': {
                'NAME': ':memory:',
            }
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Lens.org API key configuration
LENS_API_KEY = ""

# Django REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.auth_backend.WorkspaceJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10000/minute' if 'test' in sys.argv else '100/minute',
        'user': '10000/minute' if 'test' in sys.argv else '1000/minute',
        'login': '10000/minute' if 'test' in sys.argv else '5/minute',
        'chat': '10000/minute' if 'test' in sys.argv else '20/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'api.exceptions.custom_exception_handler',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Schwarz Research Intelligence REST API',
    'DESCRIPTION': 'Enterprise Systematic Literature Review (SLR), Deep-Tech Scouting, and Multimodal Extraction Platform API.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
    },
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Celery Configuration Options
import ssl

raw_redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

if raw_redis_url.startswith('rediss://'):
    cert_reqs_str = os.environ.get('REDIS_SSL_CERT_REQS', 'none').lower()
    cert_reqs_val = ssl.CERT_NONE if cert_reqs_str == 'none' else getattr(ssl, cert_reqs_str.upper(), ssl.CERT_NONE)

    if 'ssl_cert_reqs' not in raw_redis_url:
        delimiter = '&' if '?' in raw_redis_url else '?'
        raw_redis_url = f"{raw_redis_url}{delimiter}ssl_cert_reqs={cert_reqs_str}"

    CELERY_BROKER_USE_SSL = {
        'ssl_cert_reqs': cert_reqs_val
    }
    CELERY_REDIS_BACKEND_USE_SSL = {
        'ssl_cert_reqs': cert_reqs_val
    }


CELERY_BROKER_URL = raw_redis_url
CELERY_RESULT_BACKEND = raw_redis_url
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Celery Beat Periodic Scheduled Tasks (Zombie Watchdog, Workflow Dispatcher & Scheduled Digests)
CELERY_BEAT_SCHEDULE = {
    'reap-zombie-tasks-watchdog': {
        'task': 'research_intelligence.tasks.auxiliary.zombie_watchdog.reap_zombie_tasks_task',
        'schedule': 60.0,  # runs every 60 seconds
        'options': {'queue': 'celery'}
    },
    'dispatch-scheduled-workflow-runs': {
        'task': 'research_intelligence.tasks.auxiliary.schedule_dispatcher.dispatch_scheduled_workflow_runs_task',
        'schedule': 60.0,  # runs every 60 seconds
        'options': {'queue': 'celery'}
    },
    'cleanup-expired-blacklisted-tokens': {
        'task': 'research_intelligence.tasks.auxiliary.token_cleanup.cleanup_expired_tokens_task',
        'schedule': 86400.0,  # runs daily (every 24 hours)
        'options': {'queue': 'celery'}
    },
}


if is_testing:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_RESULT_BACKEND = 'cache'
    CELERY_CACHE_BACKEND = 'memory'
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

    class DisableMigrations:
        def __contains__(self, item):
            return True
        def __getitem__(self, item):
            return None
    MIGRATION_MODULES = DisableMigrations()


# Storage Abstraction for Local Filesystem, AWS S3, MinIO, and Google Cloud Storage (GCS)
# Modern Django STORAGES configuration (Django 4.2+, 5.x, 6.0 standard)
if is_testing:
    STORAGE_BACKEND = 'local'
else:
    STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local').lower()

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

if STORAGE_BACKEND in ['s3', 'minio']:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', os.environ.get('MINIO_ACCESS_KEY', 'minio_dev_user'))
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', os.environ.get('MINIO_SECRET_KEY', 'minio_dev_password'))
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'schwarz-research-intelligence')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'eu-central-1')
    
    endpoint_url = os.environ.get('AWS_S3_ENDPOINT_URL', os.environ.get('MINIO_ENDPOINT'))
    if endpoint_url:
        use_ssl = os.environ.get('AWS_S3_USE_SSL', os.environ.get('MINIO_SECURE', 'False')).lower() in ['true', '1', 'yes']
        if not endpoint_url.startswith('http'):
            protocol = "https" if use_ssl else "http"
            endpoint_url = f"{protocol}://{endpoint_url}"
        AWS_S3_ENDPOINT_URL = endpoint_url
        AWS_S3_USE_SSL = use_ssl

elif STORAGE_BACKEND in ['gcs', 'gcp']:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.gcp_storage.GoogleCloudStorage",
    }
    GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME', 'schwarz-research-intelligence')

# Legacy alias for backward compatibility with external libraries
DEFAULT_FILE_STORAGE = STORAGES["default"]["BACKEND"]


# Mailgun Email Configuration
MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', '')
MAILGUN_API_URL = os.environ.get('MAILGUN_API_URL', 'https://api.eu.mailgun.net/v3')
MAILGUN_SENDER_DOMAIN = os.environ.get('MAILGUN_SENDER_DOMAIN', 'soinventive.co.uk')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'no-reply@{MAILGUN_SENDER_DOMAIN}')

# Allow internal same-origin iframes (e.g. Storage Browser PDF preview & admin popups)
X_FRAME_OPTIONS = 'SAMEORIGIN'


# Sentry Error Tracking & Performance Monitoring
SENTRY_DSN = os.environ.get('SENTRY_DSN', '')

if SENTRY_DSN and not is_testing:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        # Add data like request headers and IP for users
        send_default_pii=True,
        # Enable sending logs to Sentry
        enable_logs=True,
        # Set traces_sample_rate to 1.0 to capture 100% of transactions for tracing
        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '1.0')),
        # Set profile_session_sample_rate to 1.0 to profile 100% of profile sessions
        profile_session_sample_rate=float(os.environ.get('SENTRY_PROFILE_SESSION_SAMPLE_RATE', '1.0')),
        # Set profile_lifecycle to "trace" to automatically run the profiler when there is an active transaction
        profile_lifecycle=os.environ.get('SENTRY_PROFILE_LIFECYCLE', 'trace'),
    )





