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
    "unfold.contrib.inlines",
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
    "polling",
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
    # Private unless a view says otherwise. DRF's own default is AllowAny,
    # which means a view that forgets the line publishes whatever it reads.
    # Boards are somebody's data, so the miss has to fail closed. The
    # catalog is public by design and says so on each view.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
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
        "task": "polling.tasks.enqueue_due_polls",
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
    # The brand palette. The accent is deliberately not the mark's green:
    # #00E54D means "operational" on every status pill, so using it for nav
    # chrome makes an active link read as a status. This is a warm sand
    # pulled from the cream #F5EDD6 instead — same family, no collision
    # with up-green or down-red. Base runs from the cream down through the
    # brand brown, so a dark page reads brown rather than black. The last
    # steps sit below the old near-black: brown reads lighter than a
    # neutral at the same value, so it has to go further down.
    "COLORS": {
        "primary": {
            "50": "#FBF8EF",
            "100": "#F4ECD7",
            "200": "#E8D9B0",
            "300": "#DAC58B",
            "400": "#CCB166",
            "500": "#BFA04A",
            "600": "#A88B3E",
            "700": "#887235",
            "800": "#6D5B2C",
            "900": "#564925",
            "950": "#352D18",
        },
        "base": {
            "50": "#FBF8EF",
            "100": "#F5EDD6",
            "200": "#E3D6BF",
            "300": "#C4B097",
            "400": "#97806A",
            "500": "#6E5847",
            "600": "#533F31",
            "700": "#3A281C",
            "800": "#241610",
            "900": "#150C06",
            "950": "#0A0503",
        },
    },
    "COMMAND": {"search_models": True, "show_history": True},
    # The sidebar is two levels deep and cannot nest an item under an item.
    # Tabs carry the relationship instead: a status history belongs to the
    # component it describes, not to a separate area of the admin. A sidebar
    # entry also stays active while you are on one of its tabs.
    # The sidebar is two levels deep and cannot nest an item under an
    # item. Tabs carry the relationship instead: a component belongs to a
    # service, and a status history to a component, so all four are one
    # page rather than four sidebar entries. A sidebar entry stays active
    # while you are on any of its tabs.
    "TABS": [
        {
            "models": [
                "catalog.service",
                "catalog.servicecomponent",
                "status.serviceevent",
                "status.componentstatus",
            ],
            "items": [
                {
                    "title": _("Services"),
                    "link": reverse_lazy("admin:catalog_service_changelist"),
                },
                {
                    "title": _("Components"),
                    "link": reverse_lazy("admin:catalog_servicecomponent_changelist"),
                },
                {
                    "title": _("Events"),
                    "link": reverse_lazy("admin:status_serviceevent_changelist"),
                },
                {
                    "title": _("Status history"),
                    "link": reverse_lazy("admin:status_componentstatus_changelist"),
                },
            ],
        },
        {
            # The beat schedule is polling machinery: it is what decides
            # when due_pollers runs at all.
            "models": [
                "polling.poller",
                "polling.pollrun",
                "django_celery_beat.periodictask",
            ],
            "items": [
                {
                    "title": _("Pollers"),
                    "link": reverse_lazy("admin:polling_poller_changelist"),
                },
                {
                    "title": _("Poll runs"),
                    "link": reverse_lazy("admin:polling_pollrun_changelist"),
                },
                {
                    "title": _("Scheduled tasks"),
                    "link": reverse_lazy(
                        "admin:django_celery_beat_periodictask_changelist"
                    ),
                },
            ],
        },
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        # One flat list. The tabs carry everything below a page now, so
        # grouping six links under four headings was more chrome than
        # navigation.
        "navigation": [
            {
                "title": _("Navigation"),
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                    {
                        "title": _("Services"),
                        "icon": "lan",
                        "link": reverse_lazy("admin:catalog_service_changelist"),
                    },
                    {
                        "title": _("Polling"),
                        "icon": "sync",
                        "link": reverse_lazy("admin:polling_poller_changelist"),
                    },
                    {
                        "title": _("Boards"),
                        "icon": "dashboard_customize",
                        "link": reverse_lazy("admin:dashboards_dashboard_changelist"),
                    },
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:authentication_user_changelist"),
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
# Lets the admin edit the tables the poller owns. For seeding a local
# database by hand. Off by default, and set only in .env.local, so it
# cannot reach a deployment.
ADMIN_EDITABLE_POLLER_DATA = os.environ.get("ADMIN_EDITABLE_POLLER_DATA") == "1"

POLL_INTERVAL_SECONDS = 300
POLL_COOLDOWN_SECONDS = 60
POLL_MAX_INTERVAL_SECONDS = 3600
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
