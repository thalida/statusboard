#!/usr/bin/env python3
"""Make sure this checkout has an api/.env.local with the local admin in it.

The file sits beside the service that reads it. An app will have its own,
and none of these variables mean anything to it.

The canonical one lives in the main checkout. A worktree copies it, so
the credentials are entered once and not once per branch.

Blank values are filled by asking. A missing file is not the trigger: the
file can exist and still have nothing in it. Asking only happens on a
terminal, which keeps CI unattended.
"""

import pathlib
import subprocess
import sys
from getpass import getpass

# The keys this script owns, and how to ask for each.
PROMPTS = {
    "DJANGO_SUPERUSER_EMAIL": ("admin email: ", input),
    "DJANGO_SUPERUSER_PASSWORD": ("admin password: ", getpass),
    "EMAIL_HOST_USER": ("fastmail address: ", input),
    "EMAIL_HOST_PASSWORD": ("fastmail app password: ", getpass),
}

# What makes a file filled in, which is not the same list. Mail is
# optional: EMAIL_USE_CONSOLE prints a sign-in link instead. So it is
# worth asking for once. Requiring it would re-ask on every init, and
# copy the shared file over a worktree's own values.
REQUIRED = ("DJANGO_SUPERUSER_EMAIL", "DJANGO_SUPERUSER_PASSWORD")

# Anchored to the checkout, not the cwd: `just` recipes cd into api/.
ROOT = pathlib.Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
TEMPLATE = ROOT / "api" / ".env.local.example"


def main_checkout() -> pathlib.Path:
    """The repository the worktrees hang off. Its file is the shared one."""
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return pathlib.Path(common).resolve().parent


def values(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def blanks(text: str, keys=None) -> list[str]:
    found = values(text)
    return [key for key in (keys or PROMPTS) if not found.get(key)]


def fill(text: str, key: str, value: str) -> str:
    """Set a key, appending it when the file predates it.

    A file written before the template grew a key does not hold it. The
    rewrite went line by line. So an answer to a prompt for a missing
    key went nowhere.
    """
    lines = [
        f"{key}={value}" if line.startswith(f"{key}=") else line
        for line in text.splitlines()
    ]
    if not any(line.startswith(f"{key}=") for line in lines):
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def starting_text(path: pathlib.Path) -> str:
    """What to build from.

    The file itself, then the one this used to live at, then the
    template. Reading the old path means nobody enters their credentials
    a second time because the file moved.
    """
    legacy = path.parent.parent / ".env.local"
    for candidate in (path, legacy):
        if candidate.exists():
            return candidate.read_text()
    return TEMPLATE.read_text()


def ensure(path: pathlib.Path) -> str:
    """Create the file if needed. Ask for anything still blank."""
    text = starting_text(path)
    missing = blanks(text)
    if missing and sys.stdin.isatty():
        print(f"Filling in {path}. Press Enter to skip any of them.")
        for key in missing:
            prompt, reader = PROMPTS[key]
            answer = reader(prompt).strip()
            if answer:
                text = fill(text, key, answer)
    # The main checkout may not have this branch, so no api/ either.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def main() -> None:
    shared = main_checkout() / "api" / ".env.local"
    local = (ROOT / "api" / ".env.local").resolve()

    text = ensure(shared)
    if shared.resolve() == local:
        return

    # A worktree. Copy the shared file unless this one already has values.
    if local.exists() and not blanks(local.read_text(), REQUIRED):
        return
    local.write_text(text)
    print(f"copied api/.env.local from {shared.parent.parent}")


if __name__ == "__main__":
    main()
