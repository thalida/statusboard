set dotenv-load
set dotenv-path := "api/.env.local"

# Per-worktree ports, compose project name and DATABASE_URL. Every recipe
# touching Postgres, Redis or the server evaluates this first. Two worktrees
# then never share a port or a database. See bin/worktree-env.py.
wt := 'eval "$(python3 bin/worktree-env.py)"'

# Keep first: bare `just` runs whatever recipe comes first.

# List the recipes.
default:
    @just --list --unsorted

# Applying migrations here is a little surprising: starting a server
# that also changes the database. The human asked for exactly this,
# since a fresh worktree that only warns still fails unexplained.

# Ctrl-C stops the server and the poller together.

# Run the app: stores, migrations, server, poller.
[group('Daily')]
dev: up migrate
    @{{wt}} ; trap 'kill 0' EXIT INT TERM ; \
      echo "http://$WORKTREE_SLUG.localhost:$DJANGO_PORT/" ; \
      cd api ; \
      uv run celery -A api worker -B -l info & \
      uv run python manage.py runserver 0.0.0.0:$DJANGO_PORT

# Arguments pass to both, so `just test -k foo` filters each.

# Run the test suite, host and bin/ scripts.
[group('Daily')]
test *args:
    @{{wt}} ; cd api && uv run pytest -n auto {{args}}
    @python3 -m unittest discover -s bin/tests -v {{args}}

# Fix lint and format the code.
[group('Daily')]
lint:
    cd api && uv run ruff check --fix . && uv run ruff format .

# Slower than `just test`, and the answer that counts: it proves the
# image rather than the host. Run it before opening a pull request.
# The two stdlib-only checks run on the host, because a container costs
# more than it saves. `bin/tests/test_merge_gate.py` holds the two lists
# together, in one direction: everything here also runs in CI.
#
# CI runs one more. It scans the image with Trivy for HIGH and CRITICAL
# CVEs and fails the merge on a hit. That needs the network and a
# vulnerability database, so it stays out of this recipe.

# Each check runs where CI runs it.

# Every CI check but the image scan.
[group('Daily')]
check: image
    docker compose -f docker-compose.test.yml run --rm pytest -q -n auto --cov-fail-under=85
    docker compose -f docker-compose.test.yml run --rm ruff
    docker compose -f docker-compose.test.yml run --rm docs
    @python3 bin/check_prose.py
    @python3 -m unittest discover -s bin/tests -v
    docker compose -f docker-compose.test.yml run --rm --entrypoint sh pytest \
      -c 'python manage.py makemigrations --check --dry-run'
    docker compose -f docker-compose.test.yml down -v

# Show this worktree's ports and database.
[group('Daily')]
info:
    @{{wt}} ; echo "worktree   $WORKTREE_SLUG" ; \
      echo "compose    $COMPOSE_PROJECT_NAME" ; \
      echo "postgres   localhost:$POSTGRES_HOST_PORT" ; \
      echo "redis      localhost:$REDIS_HOST_PORT" ; \
      echo "server     http://$WORKTREE_SLUG.localhost:$DJANGO_PORT/" ; \
      echo "client     http://$WORKTREE_SLUG.localhost:$CLIENT_PORT (reserved)"

# Check comments and docstrings against AGENTS.md.
[group('Daily')]
prose *args:
    @python3 bin/check_prose.py {{args}}

# Every step it calls is runnable on its own.

# One-time setup.
[group('Lifecycle')]
init: env up sync migrate seed
    pre-commit install
    @{{wt}} ; cd api && uv run python manage.py collectstatic --noinput

# Start Postgres and Redis, and wait for both.
[group('Lifecycle')]
up:
    @{{wt}} ; docker compose up -d --wait ; \
      echo "postgres localhost:$POSTGRES_HOST_PORT  redis localhost:$REDIS_HOST_PORT"

# Apply migrations.
[group('Lifecycle')]
migrate:
    @{{wt}} ; cd api && uv run python manage.py migrate

# Drop this database and build it again.
[group('Lifecycle')]
reset:
    @{{wt}} ; docker compose down -v ; just up ; just migrate ; just seed-live

# Also clears what an aborted `just check` left, under the compose
# project that file uses. Its database is a tmpfs, so it holds nothing.
# Add `-v` to drop this checkout's own database too.

# Stop this checkout's containers.
[group('Lifecycle')]
clean *args:
    @{{wt}} ; DIR=$(basename "$PWD") ; \
      docker compose down --remove-orphans {{args}} ; \
      docker compose -p "$DIR" -f docker-compose.test.yml down -v --remove-orphans ; \
      echo "[just] cleared compose projects $COMPOSE_PROJECT_NAME and $DIR" ; \
      if [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]; then \
          echo "[just] this checkout is a worktree. To drop it, from the main one:" ; \
          echo "[just]   git worktree remove $PWD" ; \
          echo "[just]   git branch -d $(git rev-parse --abbrev-ref HEAD)" ; \
      fi

# Fetches real status pages, so it needs the network. Fills an
# empty database: admin, a small catalog, one tracked service.

# Fill an empty database with real data.
[group('Data')]
seed-live:
    @{{wt}} ; cd api && uv run python manage.py seed_dev

# Reports any page that moved or broke.

# Probe the recorded status pages.
[group('Data')]
probe-pages *args:
    @{{wt}} ; cd api && uv run python manage.py check_status_pages {{args}}

# The tag triggers release.yml: build, sign, smoke test, deploy. A tag
# left behind by a failed push is reused rather than duplicated.

# Takes v1.2.3 or v1.2.3-rc.1.

# Tag and push a release. Ships to production.
[group('Release')]
release VERSION:
    @set -e ; \
     VERSION="{{VERSION}}" ; \
     if ! printf '%s' "$VERSION" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+(-.+)?$'; then \
         echo "[just] error: VERSION must look like v0.1.0 or v0.1.0-rc.1" >&2 ; exit 1 ; \
     fi ; \
     BRANCH=$(git rev-parse --abbrev-ref HEAD) ; \
     if [ "$BRANCH" != "main" ]; then \
         echo "[just] error: releases are tagged from main (on $BRANCH)" >&2 ; exit 1 ; \
     fi ; \
     if [ -n "$(git status --porcelain)" ]; then \
         echo "[just] error: working tree is dirty; commit or stash first" >&2 ; exit 1 ; \
     fi ; \
     git fetch --quiet origin main ; \
     LOCAL=$(git rev-parse main) ; \
     REMOTE=$(git rev-parse origin/main) ; \
     if [ "$LOCAL" != "$REMOTE" ]; then \
         echo "[just] error: main and origin/main differ; pull or push first" >&2 ; exit 1 ; \
     fi ; \
     if git ls-remote --exit-code --tags origin "refs/tags/$VERSION" >/dev/null 2>&1; then \
         echo "[just] error: tag $VERSION is already on origin" >&2 ; exit 1 ; \
     fi ; \
     CREATED=no ; \
     if git rev-parse --verify --quiet "refs/tags/$VERSION" >/dev/null; then \
         AT=$(git rev-parse "$VERSION^{commit}") ; \
         if [ "$AT" != "$LOCAL" ]; then \
             echo "[just] error: local tag $VERSION is at $AT, not main; git tag -d $VERSION and retry" >&2 ; exit 1 ; \
         fi ; \
         echo "[just] tag $VERSION already here at $LOCAL, resuming the push" ; \
     else \
         echo "[just] tagging $VERSION at $LOCAL" ; \
         git tag -a "$VERSION" -m "Release $VERSION" ; \
         CREATED=yes ; \
     fi ; \
     if ! git push origin "$VERSION"; then \
         if [ "$CREATED" = "yes" ]; then \
             echo "[just] push failed, rolling back the local tag" >&2 ; \
             git tag -d "$VERSION" >/dev/null ; \
         fi ; \
         exit 1 ; \
     fi ; \
     REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "<owner>/<repo>") ; \
     echo "[just] released. Builds, then deploys" ; \
     echo "[just] watch: https://github.com/$REPO/actions/workflows/release.yml"

# Credentials come from api/.env.local. No app argument, so this repo can
# only ever deploy its own stack.

# Redeploy without cutting a release.
[group('Release')]
deploy:
    @set -e ; \
     APP="${FORGEJO_DEPLOY_APP:-}" ; \
     MISSING="" ; \
     [ -n "${FORGEJO_HOST:-}" ]  || MISSING="$MISSING FORGEJO_HOST" ; \
     [ -n "${FORGEJO_REPO:-}" ]  || MISSING="$MISSING FORGEJO_REPO" ; \
     [ -n "${FORGEJO_TOKEN:-}" ] || MISSING="$MISSING FORGEJO_TOKEN" ; \
     [ -n "$APP" ]               || MISSING="$MISSING FORGEJO_DEPLOY_APP" ; \
     if [ -n "$MISSING" ]; then \
         echo "[just] error: api/.env.local is missing$MISSING" >&2 ; exit 1 ; \
     fi ; \
     HOST="${FORGEJO_HOST%/}" ; \
     URL="$HOST/api/v1/repos/${FORGEJO_REPO}/actions/workflows/deploy.yml/dispatches" ; \
     echo "[deploy] dispatching $APP via $FORGEJO_REPO" ; \
     CODE=$(curl -sS -o /tmp/sb-deploy-resp -w '%{http_code}' -X POST "$URL" \
         -H "Authorization: token $FORGEJO_TOKEN" \
         -H "Content-Type: application/json" \
         -d "{\"ref\":\"main\",\"inputs\":{\"app\":\"$APP\"}}") ; \
     if [ "$CODE" != "204" ] && [ "$CODE" != "201" ] && [ "$CODE" != "200" ]; then \
         echo "[just] error: Forgejo returned $CODE" >&2 ; cat /tmp/sb-deploy-resp >&2 ; echo >&2 ; exit 1 ; \
     fi ; \
     echo "[deploy] queued. Watch: $HOST/${FORGEJO_REPO}/actions"

# Everything below is a step of `init` or `check`, not a command a
# person reaches for. `just <name>` still runs each one directly.

# Asks for the admin once. A worktree copies main's.

# Write .env.local.
[private]
env:
    @python3 bin/make-env.py

# Install Python dependencies.
[private]
sync:
    cd api && uv sync

# Never asks: the values come from .env.local.

# Create the admin.
[private]
seed:
    @{{wt}} ; cd api && uv run python manage.py seed_admin

# Build the deployment image. `check` runs against this.
[private]
image:
    docker build -t statusboard-api:test api
