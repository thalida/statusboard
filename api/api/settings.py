import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development only. The file sits at the repository root and is
# never committed. A deployment has no .env.local, so load_dotenv does
# nothing and the real environment is used.
load_dotenv(BASE_DIR.parent / ".env.local")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-deploy")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")
ALLOWED_HOSTS = ["*"] if DEBUG else os.environ.get("ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.simple_history",
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
        "DIRS": [BASE_DIR / "templates"],
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

UNFOLD = {
    "SITE_TITLE": _("Statusboard"),
    "SITE_HEADER": _("Statusboard"),
    "SITE_SUBHEADER": _("Are the things you depend on working?"),
    "SITE_LOGO": {
        "light": lambda request: static("statusboard/logo-light.svg"),
        "dark": lambda request: static("statusboard/logo-dark.svg"),
    },
    "SITE_ICON": {
        "light": lambda request: static("statusboard/icon-light.svg"),
        "dark": lambda request: static("statusboard/icon-dark.svg"),
    },
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "type": "image/svg+xml",
            "href": lambda request: static("statusboard/favicon.svg"),
        }
    ],
    "LOGIN": {"image": lambda request: static("statusboard/icon-cream.svg")},
    "SITE_URL": None,
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    # Which database this is. Acting on production believing it is local
    # is the mistake worth making loud.
    "ENVIRONMENT": "common.admin.environment_callback",
    "ENVIRONMENT_TITLE_PREFIX": "common.admin.environment_prefix_callback",
    "DASHBOARD_CALLBACK": "common.admin.dashboard_callback",
    "SITE_DROPDOWN": [
        {"icon": "api", "title": _("API docs"), "link": "/"},
        {"icon": "schema", "title": _("OpenAPI schema"), "link": "/schema/"},
    ],
    # The brand palette. Primary is the operational green #00E54D with 500
    # sitting exactly on it. Base is a warm neutral running from the cream
    # #F5EDD6 down to the near-black #0D0D0D, so the admin reads as the
    # same product as the mark.
    "COLORS": {
        "primary": {
            "50": "#EBFFF1",
            "100": "#CDFEDD",
            "200": "#9DFBBC",
            "300": "#60FB94",
            "400": "#1FFF69",
            "500": "#00E54D",
            "600": "#00C241",
            "700": "#009933",
            "800": "#03772A",
            "900": "#056124",
            "950": "#013713",
        },
        "base": {
            "50": "#FBF7EC",
            "100": "#F5EDD6",
            "200": "#E5DCC4",
            "300": "#C9C0A8",
            "400": "#9C9484",
            "500": "#736C60",
            "600": "#574F45",
            "700": "#423B33",
            "800": "#2B2621",
            "900": "#1A1714",
            "950": "#0D0D0D",
        },
    },
    "COMMAND": {"search_models": True, "show_history": True},
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Overview"),
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
            {
                "title": _("Catalog"),
                "items": [
                    {
                        "title": _("Services"),
                        "icon": "lan",
                        "link": reverse_lazy("admin:catalog_service_changelist"),
                    },
                    {
                        "title": _("Components"),
                        "icon": "account_tree",
                        "link": reverse_lazy(
                            "admin:catalog_servicecomponent_changelist"
                        ),
                    },
                    {
                        "title": _("Status pages"),
                        "icon": "captive_portal",
                        "link": reverse_lazy("admin:catalog_statuspage_changelist"),
                    },
                ],
            },
            {
                "title": _("Polling"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Pollers"),
                        "icon": "sync",
                        "link": reverse_lazy("admin:catalog_poller_changelist"),
                    },
                    {
                        "title": _("Poll runs"),
                        "icon": "history",
                        "link": reverse_lazy("admin:status_pollrun_changelist"),
                    },
                    {
                        "title": _("Scheduled tasks"),
                        "icon": "schedule",
                        "link": reverse_lazy(
                            "admin:django_celery_beat_periodictask_changelist"
                        ),
                    },
                ],
            },
            {
                "title": _("Status"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Component status"),
                        "icon": "vital_signs",
                        "link": reverse_lazy("admin:status_componentstatus_changelist"),
                    },
                    {
                        "title": _("Events"),
                        "icon": "warning",
                        "link": reverse_lazy("admin:status_serviceevent_changelist"),
                    },
                ],
            },
            {
                "title": _("People"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:authentication_user_changelist"),
                    },
                    {
                        "title": _("Boards"),
                        "icon": "dashboard_customize",
                        "link": reverse_lazy("admin:dashboards_dashboard_changelist"),
                    },
                ],
            },
        ],
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "statusboard",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
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
