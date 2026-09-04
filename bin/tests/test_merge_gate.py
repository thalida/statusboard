"""`just check` and the CI workflow must gate on the same checks.

`bin/` has no dependency manager and no Django. These tests use only the
standard library, so they run on a machine that has done nothing but
`just init`. Run them with `python3 -m unittest discover -s bin/tests`.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def recipe(name):
    """One recipe's commands, with a line continuation joined up."""
    lines = []
    inside = False
    for line in JUSTFILE.read_text().splitlines():
        if re.match(rf"^{re.escape(name)}(\s|:)", line):
            inside = True
            continue
        if not inside:
            continue
        if line and not line[0].isspace():
            break
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        if lines and lines[-1].endswith("\\"):
            lines[-1] = lines[-1][:-1] + body
        else:
            lines.append(body)
    return lines


def commands():
    """Every command `just check` runs, with a called recipe inlined."""
    for line in recipe("check"):
        called = re.match(r"@?just\s+([\w-]+)", line)
        yield from recipe(called.group(1)) if called else [line]


def compose_services(command):
    """The service a `docker compose run` names, past its flags."""
    _, _, tail = command.partition("run --rm ")
    tokens = tail.split()
    while tokens:
        token = tokens.pop(0)
        if token == "--entrypoint":
            tokens.pop(0)
        elif not token.startswith("-"):
            return [token]
    return []


class MergeGateTests(unittest.TestCase):
    """CI is the gate a merge waits on. `just check` is not.

    The bin/ tests ran in `just check` and in nothing CI did. So they
    gated nothing, which is how they came to run only on a laptop.
    """

    def setUp(self):
        self.workflow = WORKFLOW.read_text()
        # Teardown, not a check. It proves nothing about the code.
        self.commands = [c for c in commands() if "down -v" not in c]

    def test_every_container_check_also_runs_in_ci(self):
        for command in self.commands:
            for service in compose_services(command):
                self.assertIn(
                    f"run --rm {service}", self.workflow, f"CI skips {service}"
                )

    def test_every_host_check_also_runs_in_ci(self):
        for command in self.commands:
            if "docker compose" in command:
                continue
            for script in re.findall(r"bin/[\w./-]+", command):
                self.assertIn(script, self.workflow, f"CI skips {script}")

    def test_the_migration_check_also_runs_in_ci(self):
        # It runs through an entrypoint override, so the service name
        # alone does not say the check itself is there.
        wanted = [c for c in self.commands if "makemigrations" in c]
        self.assertTrue(wanted, "just check no longer checks for a missing migration")
        self.assertIn("makemigrations --check --dry-run", self.workflow)


if __name__ == "__main__":
    unittest.main()
