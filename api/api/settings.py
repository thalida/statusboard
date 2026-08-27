import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# The .env sits at the repository root, one level above api/.
load_dotenv(BASE_DIR.parent / ".env")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-deploy")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")
ALLOWED_HOSTS = ["*"] if DEBUG else os.environ.get("ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "simple_history",
    "django_celery_beat",
    "rest_framework_simplejwt.token_blacklist",
    "common",
    "authentication",
    "catalog",
    "dashboards",
    "status",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "api.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://statusboard:statusboard@localhost:5432/statusboard"
    )
}

AUTH_USER_MODEL = "authentication.User"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "common.schema.FieldsAutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication"
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "common.filters.FieldsBackend",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.EnvelopePagination",
    "PAGE_SIZE": 50,
}

SIMPLE_JWT = {
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Beat runs every minute and enqueues only what is due. The interval
# itself lives on each Poller.next_at, so a service can be tuned in
# admin without touching this schedule.
CELERY_BEAT_SCHEDULE = {
    "enqueue-due-polls": {
        "task": "status.tasks.enqueue_due_polls",
        "schedule": crontab(minute="*"),
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": "statusboard",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "meta"},
        {"name": "auth"},
        {"name": "me"},
        {"name": "catalog"},
        {"name": "board"},
    ],
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Deployment defaults. A single service overrides these on its Poller row.
POLL_INTERVAL_SECONDS = 300
POLL_COOLDOWN_SECONDS = 60
POLL_MAX_INTERVAL_SECONDS = 3600
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
