"""Behaviour tests for `bin/check_prose.py`.

`bin/` has no dependency manager and no Django. These tests use only the
standard library, so they run on a machine that has done nothing but
`just init`. Run them with `python3 -m unittest discover -s bin/tests`.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_prose


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


if __name__ == "__main__":
    unittest.main()
