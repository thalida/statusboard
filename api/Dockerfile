# syntax=docker/dockerfile:1.7

# The API image. Built from this directory, so the client app can have its
# own beside it without either build seeing the other's files.
#
#   docker build -t statusboard-api:test api
#
# One image, four processes. The API, the Celery worker, beat and the
# migration step run the same code and differ only by the argument. See
# entrypoint.sh.

# Python 3.14 is a requirement, not a preference. Every key defaults to
# `uuid.uuid7`, which is standard library from 3.14 and exists nowhere
# earlier. See common/models.py.
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=api.settings \
    PATH=/srv/.venv/bin:$PATH

# The base image's apt snapshot lags published security fixes, so upgrade
# before installing. Trivy fails CI on a fixed HIGH or CRITICAL OS CVE.
# That only helps if this layer re-runs, so ci.yml excludes this stage
# from the cache: a cached copy pins the upgrade to its build date.
#
# curl serves the healthcheck below. Nothing else needs it.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# uv is the package manager here, so pip is dead weight, and its vendored
# copies of setuptools and wheel are what Trivy reports. The find guards
# the glob: a base image bump must not no-op and hand the CVEs back.
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip \
           /usr/local/lib/python3.*/site-packages/pip-*.dist-info \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.* \
    && ! find /usr/local/lib -name 'pip' -maxdepth 5 -print | grep -q .

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# The venv sits beside the source, not inside it, so a bind mount over
# /srv/api in a test container cannot hide it. See docker-compose.test.yml.
WORKDIR /srv

# Lockfile first, so editing a Python file does not reinstall Django.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY . ./api/
RUN cp /srv/api/entrypoint.sh /usr/local/bin/entrypoint \
    && chmod +x /usr/local/bin/entrypoint

WORKDIR /srv/api

# The admin's own CSS, collected at build. The container then starts with
# it, and every replica serves the same hashed names. SECRET_KEY is
# needed to import settings and is never used: nothing is signed here.
RUN SECRET_KEY=build-only ENVIRONMENT=production DEBUG=0 \
    python manage.py collectstatic --noinput --clear

# Non-root. staticfiles is written above and only read from here on.
RUN useradd --create-home --uid 10001 statusboard \
    && chown -R statusboard:statusboard /srv
USER statusboard

EXPOSE 8000

# What a restart would fix. The endpoint checks the database, because a
# pool that lost its connections recovers on one. Worker and beat serve
# no page, so the stack replaces this for them.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/ || exit 1

# Zombie reaping and signal propagation come from Docker's --init.
ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["api"]

# Populated by CI.
ARG GIT_SHA=dev
ARG VERSION=0.0.0+dev
LABEL org.opencontainers.image.title="statusboard-api" \
      org.opencontainers.image.description="One board for every status page you depend on" \
      org.opencontainers.image.source="https://github.com/thalida/statusboard" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="AGPL-3.0"
