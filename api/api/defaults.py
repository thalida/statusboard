"""The settings this project named.

The split is by who named the setting. Django or a package named it, so
`settings.py` holds it: DEBUG, SECRET_KEY, ALLOWED_HOSTS, DATABASES,
every third-party block.

We named these. The poll intervals, the page sizes, the system address,
the client's addresses, the environment.

Several are read twice. `/meta` publishes the page sizes and DRF needs
the same one. A Poller row overrides the intervals for a service.

`.env.local` is loaded here, because nothing may read a variable before
the file that supplies it. Importing this module is what loads it, and
`settings.py` imports this module first.

`ENVIRONMENT` is resolved here too, so `debug` and `secret_key` read it
rather than being handed it. A value that cannot be used raises
`ImproperlyConfigured`, which is what a settings file raises.

A duration is a timedelta unless something else fixes its type. The poll
values are seconds because they are also `PositiveIntegerField` columns
on Poller, and the API publishes them as integers. The link lifetime is
neither, so it stays a timedelta and is added to a datetime.
"""

import os
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Development only, and never committed. It sits beside this service,
# not at the repository root. An app alongside will have its own, and
# none of these variables mean anything to it. A deployment has no file,
# so this does nothing and the real environment is used.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")


class Environment(StrEnum):
    """Which deployment this is.

    The banner is coloured by it. The seeding commands refuse to run
    outside DEVELOPMENT. So a typo must not read as a fourth
    environment. `settings.py` normalises it and rejects the rest.
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def parse(cls, value):
        """Read the variable, and refuse anything that is not one of these.

        Case and stray whitespace are the shape a typo usually takes, so
        they are corrected. Anything else raises: an unrecognised value
        must not read as a fourth environment.
        """
        if not value:
            return cls.DEVELOPMENT
        try:
            return cls(value.strip().lower())
        except ValueError as error:
            raise ImproperlyConfigured(
                f"ENVIRONMENT is {value!r}. Expected one of: {', '.join(cls)}."
            ) from error


# Which deployment this is. We named it, so `debug` and `secret_key`
# in `settings.py` read it here rather than being handed it.
ENVIRONMENT = Environment.parse(os.environ.get("ENVIRONMENT"))


class Throttle(StrEnum):
    """A rate this deployment enforces.

    A view names its scope and `settings.py` gives it a rate. The two
    spellings had to match. DRF names the first two; we named the
    rest.
    """

    ANONYMOUS = "anon"
    SIGNED_IN = "user"
    IMPORT = "import"
    MAGIC_LINK = "magic-link"


# Reading the catalog is the point, so the plain rates are wide. Each of
# the others costs somebody else something: an outbound fetch, and a
# delivered email.
THROTTLE_RATES = {
    Throttle.ANONYMOUS: "120/min",
    Throttle.SIGNED_IN: "600/min",
    Throttle.IMPORT: "6/min",
    Throttle.MAGIC_LINK: "5/hour",
}


# Cursor pagination. `/meta` publishes both, so a client can size a page
# without guessing which values the server will accept.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# How often a tracked service is polled, when its Poller says nothing.
# The cooldown is the floor. Nothing is polled more often. A poller past
# due by more than one is late, not waiting.
POLL_INTERVAL_SECONDS = 300
POLL_COOLDOWN_SECONDS = 60

# Backoff doubles up to this. A provider that is down for a day is polled
# hourly, not every five minutes.
POLL_MAX_INTERVAL_SECONDS = 3600

# How long a poll run is kept. One row per service per poll, so at the
# default interval a hundred services write ten million rows a year.
# Long enough to read a week of failures, and no longer.
POLL_RUN_RETENTION_DAYS = 30

# How far back a provider's event may start and still claim one we
# opened. Providers back-date `starts_at` to when an incident really
# began, which is before our poll saw it.
EVENT_CLAIM_WINDOW = timedelta(
    seconds=int(os.environ.get("EVENT_CLAIM_WINDOW_SECONDS", "3600"))
)

# Who the system writes as. RFC 2606 reserves the domain. No mail leaves
# for it, and nobody can hold the address.
SYSTEM_EMAIL = "system@statusboard.invalid"

# How long a sign-in link works for. Long enough to walk to a phone,
# short enough that a link left in an inbox is not a key.
MAGIC_LINK_TTL = timedelta(minutes=15)


# The client app, not this service. A sign-in email links to a page the
# client serves. This project is the API on its own subdomain, so it
# cannot work either of these out. APP_URL has no default for the same
# reason: a guess would point where nothing is served.
APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")
APP_MAGIC_LINK_PATH = os.environ.get("APP_MAGIC_LINK_PATH", "").strip() or "/verify"

# The key this repository publishes. Development runs on it; nothing
# else may.
DEV_SECRET_KEY = "dev-only-not-for-deploy"


def secret_key(configured):
    """The signing key, or a refusal.

    It used to fall back to the development key everywhere. A
    deployment that forgot the variable signed every cookie and token
    with a string anybody can read here.
    """
    configured = (configured or "").strip()
    if configured:
        return configured
    if ENVIRONMENT is not Environment.DEVELOPMENT:
        raise ImproperlyConfigured(
            f"SECRET_KEY is unset, and ENVIRONMENT is {ENVIRONMENT}. Every "
            "signature this process makes would use a key in the repository."
        )
    return DEV_SECRET_KEY


def debug(configured):
    """Whether to serve tracebacks.

    It used to default on, so a deployment that forgot the variable
    showed its stack traces to callers.
    """
    if configured is not None and configured.strip():
        return configured.strip() == "1"
    return ENVIRONMENT is Environment.DEVELOPMENT
