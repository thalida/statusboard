#!/usr/bin/env python3
"""Create .env if this checkout has none.

A worktree reuses the main checkout's .env. So the admin credentials are
entered once, not once per branch.

With no .env anywhere, this copies .env.example and asks for the admin.
It only asks on a terminal, which keeps CI unattended. An empty answer
leaves the value blank, and seed_admin then asks instead.
"""

import pathlib
import shutil
import subprocess
import sys
from getpass import getpass

PROMPTS = {
    "DJANGO_SUPERUSER_EMAIL": ("admin email: ", input),
    "DJANGO_SUPERUSER_PASSWORD": ("admin password: ", getpass),
}


def main_checkout() -> pathlib.Path:
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return pathlib.Path(common).resolve().parent


def fill(text: str, key: str, value: str) -> str:
    return (
        "\n".join(
            f"{key}={value}" if line.startswith(f"{key}=") else line
            for line in text.splitlines()
        )
        + "\n"
    )


def main() -> None:
    env = pathlib.Path(".env")
    if env.exists():
        return

    shared = main_checkout() / ".env"
    if shared.exists() and shared.resolve() != env.resolve():
        shutil.copy(shared, env)
        print(f"copied .env from {shared.parent}")
        return

    text = pathlib.Path(".env.example").read_text()
    if sys.stdin.isatty():
        print("No .env yet. Set the local admin, or press Enter to skip.")
        for key, (prompt, reader) in PROMPTS.items():
            value = reader(prompt).strip()
            if value:
                text = fill(text, key, value)
    env.write_text(text)
    print("created .env")


if __name__ == "__main__":
    main()
