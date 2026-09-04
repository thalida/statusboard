#!/usr/bin/env python3
"""Hold comments and docstrings to the rules in AGENTS.md.

Three rules are mechanical, so they are checked here and not in review.
`long` is a sentence over 20 words. `dash` is an em dash or an en dash.
`block` is one comment paragraph over the line limit.

Everything else in AGENTS.md is a judgement, and stays with the reader.

Run over the files given, or over the whole repository with no
arguments. `--limit` sets the paragraph ceiling.
"""

import argparse
import ast
import io
import pathlib
import re
import sys
import tokenize

# A stop ends a sentence unless it is an abbreviation or an initial.
# `api.py` never matches: the split needs whitespace after the stop.
STOP = re.compile(r'[.!?]["\']?\s+')
ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "Dr", "Mr", "Ms", "No", "Fig"}
MAX_WORDS = 20
DASHES = {"\u2014": "em dash", "\u2013": "en dash"}
# A directive is not prose.
DIRECTIVE = re.compile(r"^#\s*(noqa|type:|ruff:|pragma:|fmt:|mypy:|!)")
CODE_ISH = re.compile(r"^\s*[\w.]+\([^)]*\)\s*$|^\s*[-*]\s|^\s{4,}\S")
# A code span, however many tokens inside, is one thing to read.
CODE_SPAN = re.compile(r"`[^`]*`")

# The repository root, from this file's own location. A hand run from
# `api/` or `bin/` then resolves the same default as one from the root.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def sentences(blocks):
    """Split prose into sentences, keeping the line each one started on."""
    for block, first_line in blocks:
        flat = " ".join(block.split())
        if not flat:
            continue
        parts, cursor = [], 0
        for match in STOP.finditer(flat):
            head = flat[cursor : match.start()]
            last = head.split()[-1] if head.split() else ""
            if last.rstrip(".") in ABBREVIATIONS or re.fullmatch(r"[A-Za-z]", last):
                continue
            parts.append(head)
            cursor = match.end()
        parts.append(flat[cursor:])
        for part in parts:
            part = part.strip()
            if part:
                yield part, first_line


def words(sentence):
    """Count words. A code span counts as one, however many it wraps.

    A span like `external_id IS NULL` is one thing to read, not three
    words to weigh. A lone backtick has no partner to pair into a
    span. It falls back to the old per-token filter, instead of
    raising.
    """
    if sentence.count("`") % 2 == 0:
        sentence = CODE_SPAN.sub("codespan", sentence)
    countable = [
        w
        for w in sentence.split()
        if not w.startswith(("`", "http://", "https://", "--"))
    ]
    return len(countable)


def comment_blocks(source):
    """Runs of `#` lines, as (text, first line number)."""
    blocks, current, start = [], [], None
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return blocks
    previous_line = None
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line, text = token.start[0], token.string
        if DIRECTIVE.match(text):
            continue
        if previous_line is not None and line != previous_line + 1:
            blocks.append((current, start))
            current, start = [], None
        if start is None:
            start = line
        current.append(text.lstrip("#").strip())
        previous_line = line
    if current:
        blocks.append((current, start))
    return [(lines, start) for lines, start in blocks if lines]


def docstrings(source):
    """Every docstring in the file, as (text, first line number)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        text = ast.get_docstring(node, clean=True)
        if text:
            line = getattr(node, "lineno", 1)
            found.append((text.splitlines(), line))
    return found


def paragraphs(lines, start):
    """Split a block on blank lines. A paragraph is one idea."""
    out, current, offset = [], [], 0
    for index, line in enumerate(lines):
        if line.strip():
            if not current:
                offset = index
            current.append(line)
        elif current:
            out.append((" ".join(current), start + offset))
            current = []
    if current:
        out.append((" ".join(current), start + offset))
    return out


def check(path, limit):
    """Every problem in one file."""
    source = path.read_text(encoding="utf-8")
    problems = []

    for lines, start in comment_blocks(source):
        # The ceiling is per paragraph. A blank `#` line is a break, so
        # a long comment is allowed if it is broken into ideas.
        for text, line in paragraphs(lines, start):
            length = len(text.split(" ")) // 11 + 1
            if length > limit:
                problems.append(
                    (line, "block", f"about {length} lines, limit is {limit}")
                )
        problems += prose_problems(paragraphs(lines, start))

    for lines, start in docstrings(source):
        problems += prose_problems(paragraphs(lines, start))

    return sorted(problems)


def prose_problems(blocks):
    """The rules that apply to any run of prose."""
    problems = []
    for sentence, line in sentences(blocks):
        if CODE_ISH.match(sentence):
            continue
        for mark, name in DASHES.items():
            if mark in sentence:
                problems.append((line, "dash", f"{name} in {sentence[:60]!r}"))
        count = words(sentence)
        if count > MAX_WORDS:
            problems.append((line, "long", f"{count} words: {sentence[:70]!r}"))
    return problems


def default_targets():
    """The directories scanned when no path is given: api/ and bin/.

    A stdlib script checks its own prose too, not only Django's.
    """
    return [REPO_ROOT / "api", REPO_ROOT / "bin"]


def default_paths():
    """Every `.py` file under a default target that exists."""
    return sorted(
        path
        for target in default_targets()
        if target.is_dir()
        for path in target.rglob("*.py")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=pathlib.Path)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    if args.paths:
        paths = args.paths
        label = ", ".join(str(p) for p in paths)
    else:
        targets = default_targets()
        if not any(target.is_dir() for target in targets):
            existing = ", ".join(str(t) for t in targets)
            print(f"error: no scan target exists: {existing}", file=sys.stderr)
            return 1
        paths = default_paths()
        label = " and ".join(
            str(t.relative_to(REPO_ROOT)) for t in targets if t.is_dir()
        )

    total = 0
    examined = 0
    for path in paths:
        if path.suffix != ".py" or not path.is_file():
            continue
        if any(part in {".venv", "__pycache__", "migrations"} for part in path.parts):
            continue
        examined += 1
        for line, rule, detail in check(path, args.limit):
            print(f"{path}:{line}: {rule}: {detail}")
            total += 1

    # A checker that examines nothing has not passed. It has not run.
    if examined == 0:
        print(f"error: no files examined in {label}.", file=sys.stderr)
        return 1
    if total:
        print(f"\n{total} problems. See AGENTS.md.", file=sys.stderr)
        return 1

    noun = "file" if examined == 1 else "files"
    print(f"Checked {examined} {noun} in {label}. Clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
