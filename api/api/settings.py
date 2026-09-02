import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

# Re-exported so `django.conf.settings` carries them. See api/defaults.py.
from api.defaults import (  # noqa: F401
    DEFAULT_PAGE_SIZE,
    MAGIC_LINK_TTL,
    MAX_PAGE_SIZE,
    POLL_COOLDOWN_SECONDS,
    POLL_INTERVAL_SECONDS,
    POLL_MAX_INTERVAL_SECONDS,
    SYSTEM_EMAIL,
    Environment,
    debug,
    secret_key,
)

BASE_DIR = Path(__file__).resolve().parent.parent

# Development only, and never committed. It sits beside this service,
# not at the repository root. An app alongside will have its own, and
# none of these variables mean anything to it. A deployment has no file,
# so load_dotenv does nothing and the real environment is used.
load_dotenv(BASE_DIR / ".env.local")
# The banner colour, the development-only commands and the two settings
# below all branch on this. A value nobody recognises stops here.
try:
    ENVIRONMENT = Environment.parse(os.environ.get("ENVIRONMENT"))
except ValueError as error:
    raise ImproperlyConfigured(str(error)) from error
DEVELOPING = ENVIRONMENT is Environment.DEVELOPMENT

# These two used to default toward development. A deployment that
# forgot either ran with tracebacks on, and with a key published in this
# repository. See `secret_key` and `debug` for what each refuses.
DEBUG = debug(os.environ.get("DEBUG"), ENVIRONMENT)
try:
    SECRET_KEY = secret_key(os.environ.get("SECRET_KEY"), ENVIRONMENT)
except ValueError as error:
    raise ImproperlyConfigured(str(error)) from error

# A wildcard accepts any Host header. The dev machine is usually on a
# network too. So debug adds the loopback names and nothing else.
# `0.0.0.0` is one: runserver binds to it. A LAN address goes in
# .env.local.
#
# `"".split(",")` is `[""]`, not `[]`. Unset, that looked configured and
# matched nothing. Blank entries are dropped, so Django refuses an empty
# list out loud.
LOCAL_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]", ".localhost"]
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()
]
if DEBUG:
    ALLOWED_HOSTS += LOCAL_HOSTS

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
    # The contract calls it `q`, and DRF's SearchFilter calls it
    # `search`. One name, and the schema documents it.
    "SEARCH_PARAM": "q",
    # The contract has always answered 429, and nothing raised one.
    # Two endpoints make that expensive rather than untidy. An import
    # fetches a URL somebody handed us. A magic link mails an address
    # nobody has proved they own.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Reading the catalog is the point, so the plain rates are wide.
        "anon": "120/min",
        "user": "600/min",
        # Each of these costs somebody else something: an outbound fetch
        # and a delivered email.
        "import": "6/min",
        "magic-link": "5/hour",
    },
    # One shape for every failure. See common/errors.py.
    "EXCEPTION_HANDLER": "common.errors.handler",
    "DEFAULT_PAGINATION_CLASS": "common.pagination.EnvelopePagination",
    # The same number `/meta` publishes and the paginator reads.
    "PAGE_SIZE": DEFAULT_PAGE_SIZE,
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
    # The mark on the ground it now stands on. The cream one is kept for
    # anywhere the light theme needs it.
    "LOGIN": {"image": lambda request: static("statusboard/icon-ultramarine.svg")},
    "SITE_URL": None,
    # One theme. The palette is ultramarine on a near-black ground and
    # the light half was never designed, only tolerated.
    "THEME": "dark",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    # Which database this is. Acting on production believing it is development
    # is the mistake worth making loud.
    "ENVIRONMENT": "common.admin.environment_callback",
    "ENVIRONMENT_TITLE_PREFIX": "common.admin.environment_prefix_callback",
    "DASHBOARD_CALLBACK": "common.admin.dashboard_callback",
    "SITE_DROPDOWN": [
        {"icon": "api", "title": _("API docs"), "link": "/"},
        {"icon": "schema", "title": _("OpenAPI schema"), "link": "/schema/"},
    ],
    # Ultramarine, and no accent hue. The mark's green means operational
    # and its red means outage. A colour the chrome borrows would read as
    # a state. Weight and contrast carry interaction instead.
    #
    # `base` runs blue-violet white to blue-violet black, so no step is a
    # grey. The dark end goes further than a neutral. A saturated hue
    # reads lighter than a grey of the same value.
    "COLORS": {
        # One theme, so one ramp. Unfold writes `bg-primary-600` once,
        # for both themes. The old ramp held ink there, for the light
        # theme, and painted it on the dark page.
        #
        # Two shades matter, and they pull apart. 500 is read as text,
        # so it is measured against the page: 5.7:1. 600 is filled and
        # carries white: 4.8:1. Neither moves without failing the other.
        #
        # Still no accent hue. These are ultramarine neutrals.
        "primary": {
            "50": "#F3F3FB",
            "100": "#E9E9F6",
            "200": "#DEDEF0",
            "300": "#C6C5E4",
            "400": "#C6C5E4",
            "500": "#8A88B8",
            "600": "#6F6F92",
            "700": "#3B3A66",
            "800": "#1A193F",
            "900": "#12123A",
            "950": "#0D0C2B",
        },
        # Unfold paints the page with base-900 and cards with base-800.
        # Borders take base-700. So four steps carry ground, surface and
        # edge. Read the roles off the templates before moving one.
        #
        # The dark steps are set by contrast, not by lightness. A deep
        # blue holds little luminance. A step on a ramp is not a step on
        # a screen.
        #
        # At 1.05:1 the card was invisible. At 1.42:1 it was a purple
        # slab, because Unfold fills whole blocks with base-800. The
        # card is 1.22:1 now, which reads as a lift.
        "base": {
            "50": "#F3F3FB",
            "100": "#E9E9F6",
            "200": "#DEDEF0",
            "300": "#C6C5E4",
            "400": "#A9A7D6",
            "500": "#8A88B8",
            "600": "#5E5E7D",
            "700": "#303043",
            "800": "#1F1F2C",
            "900": "#06061F",
            "950": "#030310",
        },
    },
    "COMMAND": {"search_models": True, "show_history": True},
    # The sidebar is two levels deep. It cannot nest an item under an
    # item, so tabs carry the relationship. A component belongs to a
    # service, and a status history to a component. All four are one
    # page. The sidebar entry stays active on any of its tabs.
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
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "Statusboard <no-reply@statusboard.app>"
)

# The client app, not this service. A sign-in email links to a page the
# client serves. This project is the API on its own subdomain, so it
# cannot work either of these out. There is no default for the same
# reason: a guess would point somewhere nothing is served.
APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")
APP_MAGIC_LINK_PATH = os.environ.get("APP_MAGIC_LINK_PATH", "").strip() or "/verify"
