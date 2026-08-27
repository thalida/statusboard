#!/usr/bin/env python3
"""Make sure this checkout has a .env.local with the local admin in it.

The canonical .env.local lives in the main checkout. A worktree copies
it. So
the credentials are entered once, not once per branch.

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
}

# Anchored to the checkout, not the cwd: `just` recipes cd into api/.
ROOT = pathlib.Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
TEMPLATE = ROOT / ".env.local.example"


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


def blanks(text: str) -> list[str]:
    found = values(text)
    return [key for key in PROMPTS if not found.get(key)]


def fill(text: str, key: str, value: str) -> str:
    lines = [
        f"{key}={value}" if line.startswith(f"{key}=") else line
        for line in text.splitlines()
    ]
    return "\n".join(lines) + "\n"


def ensure(path: pathlib.Path) -> str:
    """Create the file if needed. Ask for anything still blank."""
    text = path.read_text() if path.exists() else TEMPLATE.read_text()
    missing = blanks(text)
    if missing and sys.stdin.isatty():
        print(f"Setting the local admin in {path}. Press Enter to skip.")
        for key in missing:
            prompt, reader = PROMPTS[key]
            answer = reader(prompt).strip()
            if answer:
                text = fill(text, key, answer)
    path.write_text(text)
    return text


def main() -> None:
    shared = main_checkout() / ".env.local"
    local = (ROOT / ".env.local").resolve()

    text = ensure(shared)
    if shared.resolve() == local:
        return

    # A worktree. Copy the shared file unless this one already has values.
    if local.exists() and not blanks(local.read_text()):
        return
    local.write_text(text)
    print(f"copied .env.local from {shared.parent}")


if __name__ == "__main__":
    main()
