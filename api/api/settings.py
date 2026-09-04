import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

# Re-exported so `django.conf.settings` carries them. See api/defaults.py.
from api.defaults import (  # noqa: F401
    APP_MAGIC_LINK_PATH,
    APP_URL,
    DEFAULT_PAGE_SIZE,
    ENVIRONMENT,
    EVENT_CLAIM_WINDOW,
    MAGIC_LINK_TTL,
    MAX_PAGE_SIZE,
    POLL_COOLDOWN_SECONDS,
    POLL_INTERVAL_SECONDS,
    POLL_MAX_INTERVAL_SECONDS,
    POLL_RUN_RETENTION_DAYS,
    SYSTEM_EMAIL,
    THROTTLE_RATES,
    debug,
    secret_key,
)

BASE_DIR = Path(__file__).resolve().parent.parent

# Both used to default toward development. A deployment that forgot
# either ran with tracebacks on, and with a key published in this
# repository. Each refuses a value it cannot use, and reads ENVIRONMENT
# rather than being handed it. See api/defaults.py.
DEBUG = debug(os.environ.get("DEBUG"))
SECRET_KEY = secret_key(os.environ.get("SECRET_KEY"))

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
    # The deployment has no web server in front of Django, only a router.
    # So the admin's own CSS is served by this process or by nothing.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "api.urls"
WSGI_APPLICATION = "api.wsgi.application"
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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashed names, so a changed file gets a new URL and no cache serves
    # the old one. The manifest is written by `collectstatic`, and asking
    # for a file missing from it raises. That is what a deployment wants
    # and what development cannot have: the suite does not collect.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
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
    # The contract has always answered 429, and nothing raised one. See
    # `Throttle` for what each rate is protecting.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": THROTTLE_RATES,
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
#
# A task is named by its dotted path, because settings loads before the
# app registry and cannot import one. A test resolves every name here
# against what Celery registered, so a rename cannot go quiet.
CELERY_BEAT_SCHEDULE = {
    "enqueue-due-polls": {
        "task": "polling.tasks.enqueue_due_polls",
        "schedule": crontab(minute="*"),
    },
    # Nothing removed a poll run, and one is written per service per
    # poll. Daily is often enough for a thirty day window.
    "forget-old-poll-runs": {
        "task": "polling.tasks.forget_old_poll_runs",
        "schedule": crontab(hour="4", minute="20"),
    },
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
    # Ultramarine, one theme, no accent hue. Unfold names the step it
    # paints, so a shade is fixed by where it lands rather than by a
    # ramp. Read the roles off the templates before moving one.
    #
    #   primary-500  text on the page      5.7:1
    #   primary-600  filled, under white   4.8:1
    #   base-900 page   base-800 cards   base-700 edges
    #
    # Neither primary shade moves without failing the other. The dark
    # base steps are set by contrast, not lightness. A deep blue holds
    # little luminance, so a step on a ramp is not one on a screen. The
    # card is 1.22:1. At 1.05:1 it was invisible, at 1.42:1 a slab.
    "COLORS": {
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
        {"name": "status"},
        {"name": "board"},
    ],
}

# A magic link is the only way to sign in, so a deployment that cannot
# send mail cannot be used. EMAIL_HOST decides: set, the mail is sent;
# unset, it is printed, which is what development wants.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = EMAIL_PORT != 465
EMAIL_USE_SSL = EMAIL_PORT == 465
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "Statusboard <no-reply@statusboard.dev>"
)

# The client app is on another origin, so the browser asks first. A
# blank list refuses every origin, which is the safe way to be wrong.
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# The admin posts forms from this host, over HTTPS. Django checks the
# scheme too, so the host alone is not enough.
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

if not DEBUG:
    # TLS is terminated by the router in front of this process, so the
    # request arrives on plain HTTP. Without this Django reads every
    # request as insecure and redirects a secure one forever.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    # The container asks itself over loopback, on plain HTTP. Redirecting
    # that answers 301. curl reads a 301 as success. The check then
    # passes without ever reaching Django.
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
