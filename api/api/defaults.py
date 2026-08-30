"""The numbers this project chose, in one place.

Django's settings and every third-party block stay in `settings.py`.
These are ours, and several of them are read twice: the API publishes the
page sizes at `/meta`, DRF needs the same page size, and a Poller row
overrides the poll intervals for one service.

No environment is read here. `settings.py` loads `.env.local` before it
reads any variable, so anything from the environment belongs there.
"""

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
