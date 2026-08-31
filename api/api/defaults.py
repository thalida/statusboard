"""The numbers this project chose, in one place.

Django's settings and every third-party block stay in `settings.py`.
These are ours, and several are read twice. `/meta` publishes the page
sizes. DRF needs the same page size. A Poller row overrides the poll
intervals for one service.

No environment is read here. `settings.py` loads `.env.local` before it
reads any variable, so anything from the environment belongs there.

A duration is a timedelta unless something else fixes its type. The poll
values are seconds because they are also `PositiveIntegerField` columns
on Poller, and the API publishes them as integers. The link lifetime is
neither, so it stays a timedelta and is added to a datetime.
"""

from datetime import timedelta
from enum import StrEnum


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
            raise ValueError(
                f"ENVIRONMENT is {value!r}. Expected one of: {', '.join(cls)}."
            ) from error


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

# Who the system writes as. RFC 2606 reserves the domain. No mail leaves
# for it, and nobody can hold the address.
SYSTEM_EMAIL = "system@statusboard.invalid"

# How long a sign-in link works for. Long enough to walk to a phone,
# short enough that a link left in an inbox is not a key.
MAGIC_LINK_TTL = timedelta(minutes=15)
