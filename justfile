set dotenv-load
set dotenv-filename := ".env.local"

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

# Write .env.local, asking for the admin once. Worktrees copy main's.
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

# Stop them, keeping the data. `just down -v` drops this worktree's database.
down *args:
    @{{wt}} ; docker compose down {{args}}

# Install Python dependencies.
sync:
    cd api && uv sync

# Apply migrations to this worktree's database.
migrate:
    @{{wt}} ; cd api && uv run python manage.py migrate

# Create the admin in this worktree's database, from .env.local. Never asks.
seed:
    @{{wt}} ; cd api && uv run python manage.py seed_admin

# Fill an empty local database: the admin, a small catalog, one tracked
# service. Fetches three real status pages, so it needs the network.
seed-dev:
    @{{wt}} ; cd api && uv run python manage.py seed_dev

# Drop this worktree's database and build it again from nothing.
reset:
    @{{wt}} ; docker compose down -v ; just up ; just migrate ; just seed-dev

# Probe the recorded status pages and report any that moved or broke.
check-pages *args:
    @{{wt}} ; cd api && uv run python manage.py check_status_pages {{args}}

# Run the test suite.
test:
    @{{wt}} ; cd api && uv run pytest -n auto

# Run the test suite with the coverage gate.
test-cov:
    @{{wt}} ; cd api && uv run pytest -n auto --cov-fail-under=85

# Fix lint and format the code.
lint:
    cd api && uv run ruff check --fix . && uv run ruff format .

# Run the app: server and poller together. Ctrl-C stops both.
dev:
    @{{wt}} ; trap 'kill 0' EXIT INT TERM ; \
      echo "http://localhost:$DJANGO_PORT/" ; \
      cd api ; \
      uv run celery -A api worker -B -l info & \
      uv run python manage.py runserver 0.0.0.0:$DJANGO_PORT
