# llm-output-ini-section-duplicate-detector

## What it detects

INI-style files (`tox.ini`, `setup.cfg`, `alembic.ini`, `.gitconfig`,
systemd unit overrides, classic `pylintrc`, etc.) where the same
`[section]` header appears more than once. Behavior across parsers
varies and is almost always wrong from the author's point of view:

- Python's `configparser` raises `DuplicateSectionError` (default).
- Many lenient parsers silently merge sections, so later keys clobber
  earlier ones.
- Some keep only the last block, dropping every earlier key.

LLMs that compose larger INI files from multiple snippets routinely
emit two `[testenv]` or `[flake8]` blocks. The downstream behavior is
parser-dependent, so the file may "work" locally and fail in CI.

The detector is code-fence aware: triple-backtick or triple-tilde
fenced blocks toggle "ignore" mode, so you can point it at a markdown
blob containing INI snippets without preprocessing.

## When to use

- After an LLM produces or edits a `tox.ini` / `setup.cfg` / similar.
- In CI, against any committed INI file, to guarantee single-section
  semantics regardless of parser.
- As a post-processor on assistant output that may contain fenced
  INI blocks.

## Sample input — `example_bad.ini`

```ini
[tox]
envlist = py311

[testenv]
deps = pytest
commands = pytest

[testenv:lint]
deps = ruff
commands = ruff check .

[testenv]
deps = pytest-cov
commands = pytest --cov

[flake8]
max-line-length = 100

[flake8]
extend-ignore = E203
```

## Sample output

```
$ python3 detector.py example_bad.ini
FOUND 2 duplicated section(s):
  [testenv] appears on lines 5, 13
  [flake8] appears on lines 17, 20
```

```
$ python3 detector.py example_good.ini
OK: no duplicate sections
```

Exit code is `1` when findings exist, `0` otherwise.

## Files

- `detector.py` — pure stdlib, ~55 lines.
- `example_bad.ini` — triggers 2 findings.
- `example_good.ini` — passes cleanly.
