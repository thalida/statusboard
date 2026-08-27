set dotenv-load

init:
    docker compose up -d --wait
    cd api && uv sync
    pre-commit install
    cd api && uv run python manage.py migrate
    cd api && uv run python manage.py collectstatic --noinput

test:
    cd api && uv run pytest -n auto

test-cov:
    cd api && uv run pytest -n auto --cov-fail-under=85

lint:
    cd api && uv run ruff check --fix . && uv run ruff format .

serve:
    cd api && uv run python manage.py runserver

worker:
    cd api && uv run celery -A api worker -B -l info
