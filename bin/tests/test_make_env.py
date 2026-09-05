"""`bin/make-env.py` writes the answers it is given.

`bin/` has no dependency manager and no Django. These use only the
standard library, so they run after nothing but `just init`.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("make_env", ROOT / "bin" / "make-env.py")
make_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(make_env)


class FillTests(unittest.TestCase):
    def test_an_existing_key_is_replaced_in_place(self):
        # The file keeps its comments and its order. A rewrite that
        # reordered it would make every diff unreadable.
        text = "A=1\nEMAIL_HOST_USER=\nB=2\n"
        self.assertEqual(
            make_env.fill(text, "EMAIL_HOST_USER", "me@example.com"),
            "A=1\nEMAIL_HOST_USER=me@example.com\nB=2\n",
        )

    def test_a_key_the_file_predates_is_appended(self):
        # Were it dropped, a developer would be asked for a password
        # every init and it would go nowhere each time.
        out = make_env.fill("A=1\n", "EMAIL_HOST_PASSWORD", "secret")
        self.assertIn("EMAIL_HOST_PASSWORD=secret", out)

    def test_a_prefix_of_another_key_is_not_mistaken_for_it(self):
        # EMAIL_HOST and EMAIL_HOST_USER share a prefix. Matching on
        # the name alone would set the wrong one.
        out = make_env.fill("EMAIL_HOST_USER=\n", "EMAIL_HOST", "smtp.example.com")
        self.assertIn("EMAIL_HOST_USER=", out)
        self.assertIn("EMAIL_HOST=smtp.example.com", out)


class RequiredTests(unittest.TestCase):
    def test_mail_is_asked_for_but_not_required(self):
        # Requiring it would re-ask on every init, and copy the shared
        # file over a worktree's own values.
        self.assertIn("EMAIL_HOST_PASSWORD", make_env.PROMPTS)
        self.assertNotIn("EMAIL_HOST_PASSWORD", make_env.REQUIRED)

    def test_a_file_with_the_admin_in_it_counts_as_filled(self):
        text = "DJANGO_SUPERUSER_EMAIL=a@b.c\nDJANGO_SUPERUSER_PASSWORD=x\n"
        self.assertEqual(make_env.blanks(text, make_env.REQUIRED), [])


if __name__ == "__main__":
    unittest.main()
