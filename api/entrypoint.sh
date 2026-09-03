#!/bin/sh
# One image, three processes. The first argument picks which.
set -e

case "$1" in
migrate)
    # Runs to completion, and everything else waits on it. Three
    # processes share this database: beat reads a table it cannot create
    # itself, so migrating inside one of them leaves the other two
    # racing an empty schema.
    exec /srv/.venv/bin/python manage.py migrate --noinput
    ;;
api)
    exec /srv/.venv/bin/gunicorn api.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-3}" \
        --timeout "${GUNICORN_TIMEOUT:-30}" \
        --access-logfile - \
        --error-logfile -
    ;;
worker)
    # A poll is network-bound, so threads beat processes here.
    exec /srv/.venv/bin/celery -A api worker \
        --loglevel "${CELERY_LOG_LEVEL:-info}" \
        --concurrency "${CELERY_CONCURRENCY:-4}"
    ;;
beat)
    # The schedule lives in the database, so this starts only after the
    # migrate service has finished.
    exec /srv/.venv/bin/celery -A api beat \
        --loglevel "${CELERY_LOG_LEVEL:-info}" \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
*)
    # Anything else is run as given, which is what `manage.py shell` and
    # a one-off command need.
    exec "$@"
    ;;
esac
