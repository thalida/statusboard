"""Behaviour tests for `bin/check_prose.py`.

`bin/` has no test runner of its own, and the only one in this repo is
this Django suite. `check_prose.py` needs no Django, so it is loaded
by path rather than inventing a second runner for one script.
"""

import importlib.util
from pathlib import Path

CHECK_PROSE = Path(__file__).resolve().parents[2] / "bin" / "check_prose.py"


def _load_check_prose():
    spec = importlib.util.spec_from_file_location("check_prose", CHECK_PROSE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_prose = _load_check_prose()


def test_a_multi_word_code_span_counts_as_one_word():
    # The old filter dropped only the opening token. A five-word span
    # leaked four words into the count instead of naming one.
    with_span = check_prose.words("Reject the row unless `external_id IS NULL` matches")
    without_span = check_prose.words("Reject the row unless matches")
    assert with_span == without_span + 1


def test_a_single_token_code_span_still_counts_as_one_word():
    # The old filter dropped a lone backtick-prefixed token outright,
    # so a sentence naming one field was undercounted by one.
    assert check_prose.words(
        "Reject the row unless `external_id` matches"
    ) == check_prose.words("Reject the row unless `external_id IS NULL` matches")


def test_a_code_span_followed_by_a_comma_counts_only_the_span():
    # A padded substitution once tore the comma into its own token,
    # counting a span and its punctuation as two words.
    assert check_prose.words("The `foo`, which is set, wins") == 6


def test_a_code_span_followed_by_a_full_stop_counts_only_the_span():
    # Same bug at a sentence end. The period must not become a free
    # word once the span collapses.
    assert check_prose.words("Set by `foo`. Then read") == 5


def test_an_unmatched_backtick_does_not_raise():
    # sentences() can in principle hand words() a fragment holding half
    # a span. That must fall back to counting, not crash the checker.
    assert check_prose.words("A stray ` mark stays here") == 5


def test_a_twenty_word_sentence_is_not_flagged():
    sentence = " ".join(["word"] * 20)
    assert not check_prose.prose_problems([(sentence, 1)])


def test_a_twenty_one_word_sentence_is_flagged():
    sentence = " ".join(["word"] * 21)
    problems = check_prose.prose_problems([(sentence, 1)])
    assert [rule for _line, rule, _detail in problems] == ["long"]
