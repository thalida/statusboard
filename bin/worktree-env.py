#!/usr/bin/env python3
"""Print the shell exports that make this worktree's services its own.

Usage: eval "$(python3 bin/worktree-env.py)"

Two worktrees cannot both bind 5432. Sharing one Postgres is worse. One
branch's migrations would rewrite the other branch's data.

So each worktree gets its own host ports. It also gets its own compose
project. That scopes the pgdata volume to the project. Ports and data are
both separate.

Ports are saved to .local/worktree-ports.json. A saved port is a hard
commitment. This never re-allocates silently. A bookmarked URL keeps
working. If something else takes the port, the bind fails loudly. Free the
port. Do not move it quietly.

The compose project name comes from the branch. On a detached HEAD it falls
back to the directory basename.

Each worktree answers on <slug>.localhost. A cookie ignores the port but
not the host. One localhost jar would otherwise leak an admin session
between branches.

The client app is a separate origin, so CORS and CSRF follow that host. A
value already in the environment wins, because someone may be running a
client this cannot see.

APP_URL is left alone. A sign-in link should fail rather than mail an
address nothing serves. See api/.env.local.example.
"""

import json
import os
import pathlib
import re
import socket
import subprocess

# The services this worktree needs a private host port for. No client app
# exists yet. Its port is reserved anyway, so the origins below never move
# when it arrives.
KNOWN_KEYS = ("postgres", "redis", "django", "client")

DB_USER = DB_PASSWORD = DB_NAME = "statusboard"


def worktree_root() -> pathlib.Path:
    """This checkout's top level.

    Every path here is anchored to it. Resolving against the cwd would
    hand a different port file to anyone running from api/. The
    containers would stay bound to the first one.
    """
    return pathlib.Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


def slug() -> str:
    try:
        name = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        name = ""  # detached HEAD
    name = name or worktree_root().name
    return re.sub(r"-+$", "", re.sub(r"[^a-z0-9]+", "-", name.lower())) or "statusboard"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def ports() -> dict[str, int]:
    path = worktree_root() / ".local/worktree-ports.json"
    path.parent.mkdir(exist_ok=True)
    raw = json.loads(path.read_text()) if path.exists() else {}
    # Drop anything not in the current schema so the file converges.
    data = {k: v for k, v in raw.items() if k in KNOWN_KEYS}
    for key in KNOWN_KEYS:
        if key not in data:
            data[key] = free_port()
    if data != raw:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def main() -> None:
    picked = ports()
    name = slug()
    # Postgres and Redis are reached over TCP, not from a browser, so they
    # stay on plain localhost. The driver resolves it and gains nothing
    # from a subdomain.
    exports = {
        "COMPOSE_PROJECT_NAME": f"statusboard-{name}",
        "WORKTREE_SLUG": name,
        "POSTGRES_HOST_PORT": picked["postgres"],
        "REDIS_HOST_PORT": picked["redis"],
        "DJANGO_PORT": picked["django"],
        "CLIENT_PORT": picked["client"],
        "DATABASE_URL": (
            f"postgres://{DB_USER}:{DB_PASSWORD}"
            f"@localhost:{picked['postgres']}/{DB_NAME}"
        ),
        "REDIS_URL": f"redis://localhost:{picked['redis']}/0",
    }
    # Settings read both as plain environment variables, so a worktree
    # needs no edit to answer its own client.
    client = f"http://{name}.localhost:{picked['client']}"
    for key in ("CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS"):
        if not os.environ.get(key):
            exports[key] = client
    for key, value in exports.items():
        print(f"export {key}={value}")


if __name__ == "__main__":
    main()
