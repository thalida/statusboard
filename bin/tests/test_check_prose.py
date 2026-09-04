"""Behaviour tests for `bin/check_prose.py`.

`bin/` has no dependency manager and no Django. These tests use only the
standard library, so they run on a machine that has done nothing but
`just init`. Run them with `python3 -m unittest discover -s bin/tests`.
"""

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_prose

SCRIPT = Path(check_prose.__file__).resolve()


class WordsTests(unittest.TestCase):
    def test_a_multi_word_code_span_counts_as_one_word(self):
        # The old filter dropped only the opening token. A five-word span
        # leaked four words into the count instead of naming one.
        with_span = check_prose.words(
            "Reject the row unless `external_id IS NULL` matches"
        )
        without_span = check_prose.words("Reject the row unless matches")
        self.assertEqual(with_span, without_span + 1)

    def test_a_single_token_code_span_still_counts_as_one_word(self):
        # The old filter dropped a lone backtick-prefixed token outright,
        # so a sentence naming one field was undercounted by one.
        self.assertEqual(
            check_prose.words("Reject the row unless `external_id` matches"),
            check_prose.words("Reject the row unless `external_id IS NULL` matches"),
        )

    def test_a_code_span_followed_by_a_comma_counts_only_the_span(self):
        # A padded substitution once tore the comma into its own token,
        # counting a span and its punctuation as two words.
        self.assertEqual(check_prose.words("The `foo`, which is set, wins"), 6)

    def test_a_code_span_followed_by_a_full_stop_counts_only_the_span(self):
        # Same bug at a sentence end. The period must not become a free
        # word once the span collapses.
        self.assertEqual(check_prose.words("Set by `foo`. Then read"), 5)

    def test_an_unmatched_backtick_does_not_raise(self):
        # sentences() can in principle hand words() a fragment holding half
        # a span. That must fall back to counting, not crash the checker.
        self.assertEqual(check_prose.words("A stray ` mark stays here"), 5)


class ProseProblemsTests(unittest.TestCase):
    def test_a_twenty_word_sentence_is_not_flagged(self):
        sentence = " ".join(["word"] * 20)
        self.assertFalse(check_prose.prose_problems([(sentence, 1)]))

    def test_a_twenty_one_word_sentence_is_flagged(self):
        sentence = " ".join(["word"] * 21)
        problems = check_prose.prose_problems([(sentence, 1)])
        self.assertEqual([rule for _line, rule, _detail in problems], ["long"])


class DefaultTargetTests(unittest.TestCase):
    def test_default_paths_are_the_same_from_the_repository_root_and_a_subdirectory(
        self,
    ):
        # The default used to resolve "api" against the caller's cwd.
        # A run from api/ then scanned api/api/, a handful of settings
        # files, instead of api/. The default must not depend on cwd.
        cwd = os.getcwd()
        try:
            os.chdir(check_prose.REPO_ROOT)
            from_root = check_prose.default_paths()
            os.chdir(check_prose.REPO_ROOT / "api")
            from_subdir = check_prose.default_paths()
        finally:
            os.chdir(cwd)
        self.assertEqual(from_root, from_subdir)
        self.assertTrue(from_root, "the default target found no files at all")

    def test_a_missing_default_target_is_not_silently_skipped(self):
        # A target that used to hold Python and no longer does must
        # fail loudly. It must not report a clean run over nothing.
        real_targets = check_prose.default_targets
        real_argv = sys.argv
        check_prose.default_targets = lambda: [check_prose.REPO_ROOT / "does-not-exist"]
        sys.argv = ["check_prose.py"]
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                status = check_prose.main()
        finally:
            check_prose.default_targets = real_targets
            sys.argv = real_argv
        self.assertNotEqual(status, 0)
        self.assertIn("no scan target exists", err.getvalue())


class MainExitStatusTests(unittest.TestCase):
    """Run the real script as a subprocess: main()'s exit code is the contract."""

    def run_script(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )

    def test_a_clean_default_run_exits_zero_and_names_what_it_scanned(self):
        result = self.run_script(cwd=str(check_prose.REPO_ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        # Silence on success is what let two runs from api/ report clean
        # while checking a handful of settings files. The count must show.
        self.assertIn("Checked", result.stdout)
        self.assertIn("api", result.stdout)
        self.assertIn("bin", result.stdout)

    def test_the_default_run_is_identical_from_the_repository_root_and_bin(self):
        from_root = self.run_script(cwd=str(check_prose.REPO_ROOT))
        from_bin = self.run_script(cwd=str(check_prose.REPO_ROOT / "bin"))
        self.assertEqual(from_root.returncode, 0, from_root.stderr)
        self.assertEqual(from_root.stdout, from_bin.stdout)

    def test_an_explicit_path_matching_no_file_exits_non_zero(self):
        # A caller who passes a path that matches nothing has the same
        # silent-pass problem as a broken default. Treated the same way.
        result = self.run_script("does/not/exist.py", cwd=str(check_prose.REPO_ROOT))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no files examined", result.stderr)

    def test_an_explicit_directory_with_no_python_files_exits_non_zero(self):
        # check() only ever receives files listed directly in args.paths,
        # so a directory argument matches zero files. That must error,
        # not report a clean run.
        result = self.run_script("docs", cwd=str(check_prose.REPO_ROOT))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no files examined", result.stderr)


if __name__ == "__main__":
    unittest.main()
