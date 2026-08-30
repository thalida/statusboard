"""The numbers this project chose, in one place.

Django's settings and every third-party block stay in `settings.py`.
These are ours, and several of them are read twice: the API publishes the
page sizes at `/meta`, DRF needs the same page size, and a Poller row
overrides the poll intervals for one service.

No environment is read here. `settings.py` loads `.env.local` before it
reads any variable, so anything from the environment belongs there.
"""

from datetime import timedelta
from enum import StrEnum


class Environment(StrEnum):
    """Which deployment this is.

    The admin banner is coloured by it and the seeding commands refuse to
    run outside LOCAL, so a typo must not read as an unknown environment.
    `settings.py` normalises the variable and rejects anything else.
    """

    LOCAL = "local"
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
            return cls.LOCAL
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
# The cooldown is the floor: nothing is polled more often than this, and
# a poller past due by more than one is late rather than waiting.
POLL_INTERVAL_SECONDS = 300
POLL_COOLDOWN_SECONDS = 60

# Backoff doubles up to this. A provider that is down for a day is polled
# hourly, not every five minutes.
POLL_MAX_INTERVAL_SECONDS = 3600


# Who the system writes as. The domain is reserved by RFC 2606, so no
# mail can leave for it and no person can ever hold the address.
SYSTEM_EMAIL = "system@statusboard.invalid"

# How long a sign-in link works for. Long enough to walk to a phone,
# short enough that a link left in an inbox is not a key.
MAGIC_LINK_TTL = timedelta(minutes=15)
