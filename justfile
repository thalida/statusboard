set dotenv-load

# Per-worktree ports, compose project name and DATABASE_URL. Every recipe
# touching Postgres, Redis or the server evaluates this first. Two worktrees
# then never share a port or a database. See bin/worktree-env.py.
wt := 'eval "$(python3 bin/worktree-env.py)"'

# List the recipes. Keep first: bare `just` runs whatever recipe comes first.
default:
    @just --list

# One-time setup. Every step it calls is runnable on its own.
init: env up sync migrate seed
    pre-commit install
    @{{wt}} ; cd api && uv run python manage.py collectstatic --noinput

# Write .env, asking for the admin once. Worktrees copy the main checkout's.
env:
    @python3 bin/make-env.py

# Show this worktree's ports, database and compose project.
info:
    @{{wt}} ; echo "worktree   $WORKTREE_SLUG" ; \
      echo "compose    $COMPOSE_PROJECT_NAME" ; \
      echo "postgres   localhost:$POSTGRES_HOST_PORT" ; \
      echo "redis      localhost:$REDIS_HOST_PORT" ; \
      echo "server     http://localhost:$DJANGO_PORT/"

# Start Postgres and Redis for this worktree, waiting until they are healthy.
up:
    @{{wt}} ; docker compose up -d --wait ; \
      echo "postgres localhost:$POSTGRES_HOST_PORT  redis localhost:$REDIS_HOST_PORT"

# Stop them, keeping the data. Pass -v yourself to drop this worktree's database.
down:
    @{{wt}} ; docker compose down

# Install Python dependencies.
sync:
    cd api && uv sync

# Apply migrations to this worktree's database.
migrate:
    @{{wt}} ; cd api && uv run python manage.py migrate

# Create the admin in this worktree's database, from .env. Never asks.
seed:
    @{{wt}} ; cd api && uv run python manage.py seed_admin

# Run the test suite.
test:
    @{{wt}} ; cd api && uv run pytest -n auto

# Run the test suite with the coverage gate.
test-cov:
    @{{wt}} ; cd api && uv run pytest -n auto --cov-fail-under=85

# Fix lint and format the code.
lint:
    cd api && uv run ruff check --fix . && uv run ruff format .

# Run the server and the poller together. Ctrl-C stops both.
dev:
    @trap 'kill 0' EXIT INT TERM ; just worker & just serve

# Run the dev server on this worktree's port.
serve:
    @{{wt}} ; echo "http://localhost:$DJANGO_PORT/" ; \
      cd api && uv run python manage.py runserver 0.0.0.0:$DJANGO_PORT

# Run the Celery worker and beat scheduler.
worker:
    @{{wt}} ; cd api && uv run celery -A api worker -B -l info
