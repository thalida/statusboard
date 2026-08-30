import os
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

# Re-exported so `django.conf.settings` carries them. See api/defaults.py.
from api.defaults import (  # noqa: F401
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    POLL_COOLDOWN_SECONDS,
    POLL_INTERVAL_SECONDS,
    POLL_MAX_INTERVAL_SECONDS,
)

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development only. The file sits at the repository root and is
# never committed. A deployment has no .env.local, so load_dotenv does
# nothing and the real environment is used.
load_dotenv(BASE_DIR.parent / ".env.local")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-deploy")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")
# A wildcard accepts any Host header, and a laptop running the dev server
# is usually also on a network. Debug adds the loopback names the server
# is actually reached by, and nothing else. `0.0.0.0` is one of them
# because that is what runserver binds to and what gets typed. Anything
# further, a phone on the same wifi hitting the machine's LAN address,
# goes in ALLOWED_HOSTS in .env.local.
#
# `"".split(",")` is `[""]`, not `[]`: a deployment with the variable
# unset would have looked configured and matched nothing. Empty entries
# are dropped so it stays empty, which Django refuses out loud.
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
    # Which database this is. Acting on production believing it is local
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
        # One theme, so one ramp. `primary` used to hold bone at the
        # steps the dark theme reads and ink at the steps the light one
        # reads, which only worked where Unfold pairs a class with a
        # `dark:` variant. It does not always: `bg-primary-600` under
        # white text and the current page number are written once, for
        # both themes, and both took the light theme's ink on the dark
        # page. Forcing the theme lets these be one ordinary ramp.
        #
        # Two roles decide the two shades that matter, and they pull
        # against each other. 500 is read as text (the link, fifty
        # places), so it is measured against the page: 5.7:1. 600 is
        # filled and carries white (buttons, the add link, the site
        # icon), so it is measured against white: 4.8:1. Neither can be
        # pushed further without failing the other.
        #
        # Still no accent hue. These are the ultramarine neutrals, so a
        # link is the ground lightened rather than a colour that would
        # read as a state.
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
        # Unfold paints the dark page with base-900, its cards with
        # base-800 and its borders with base-700, and the light page with
        # base-50. So those four steps carry the palette's ground,
        # surface and edge rather than sitting wherever an even ramp
        # would put them. Read the step roles off the templates before
        # moving any of these.
        #
        # The dark steps are set by contrast against the page, not by
        # lightness: a deep blue holds very little luminance, so a step
        # that looks like a step on a ramp is not one on a screen.
        #
        # Two failures got us here. At 1.05:1 the card was invisible and
        # a table could not be read. At 1.42:1 with 30% saturation it
        # was a purple slab, because Unfold fills whole blocks with
        # base-800 — a section header, an active tab — not just card
        # backgrounds. The card is 1.22:1 at 18% saturation now, which
        # reads as a lift rather than as a colour.
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

# For seeding a local database by hand. Only .env.local sets it.
ADMIN_EDITABLE_POLLER_DATA = os.environ.get("ADMIN_EDITABLE_POLLER_DATA") == "1"
