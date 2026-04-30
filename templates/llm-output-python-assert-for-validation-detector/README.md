# llm-output-python-assert-for-validation-detector

Pure-stdlib python3 single-pass scanner that flags **`assert`
used for runtime validation in production code**. The classic
CWE-617 ("Reachable Assertion") footgun — once the module runs
under `python -O` / `PYTHONOPTIMIZE=1` every `assert` vanishes
and the validation it provided disappears with it.

## What it catches

The compiler removes `assert` statements when optimisation is
enabled, which is fine for documenting invariants in a test
suite but disastrous when the assertion is the only thing
standing between a request and an unauthorised action:

```python
def withdraw(account, amount):
    assert account.owner == current_user(), "not authorised"
    assert amount <= account.balance, "overdraft"
    account.balance -= amount
```

Run that under `python -O` and both checks vanish — anyone can
drain any account. The CPython docs explicitly warn against this
pattern, yet LLMs emit it constantly because `assert` is shorter
than `if not ...: raise ValueError(...)`.

The scanner emits a single finding kind: `assert-as-validation`.

## What it does NOT flag

- `assert` inside `def test_...` functions
- `assert` inside `setUp` / `tearDown`
- `assert` in any file under a `tests/` or `test/` directory
- `assert` in `test_*.py`, `*_test.py`, `conftest.py`
- Top-level / module-scope `assert` (typically static-analyser
  hints like `assert sys.version_info >= (3, 8)`)
- Lines marked with a trailing `# assert-ok` comment
- Occurrences inside `#` comments or string / docstring literals

## Files

- `detect.py` — single-file python3 stdlib scanner. Pure
  line-based — does not import `ast`, so it stays robust on
  syntactically broken LLM snippets.
- `examples/bad/` — five `.py` files exercising the realistic
  shapes (authorization check, input validation, nested-function
  assertion, parser bounds check, async handler).
- `examples/good/` — five `.py` files exercising the safe
  shapes (proper `raise`, audited-and-suppressed type narrow,
  docstring-only mention, module-level version check, real
  `test_` function).
- `verify.sh` — runs the detector against `bad/` and `good/`
  and asserts the expected counts and exit codes.

## Run

```bash
bash verify.sh
```

Expected: `PASS`, with at least 5 findings against `bad/` and 0
against `good/`.

## Safe replacement pattern

```python
def withdraw(account, amount, current_user):
    if account.owner != current_user:
        raise PermissionError("not authorised")
    if amount > account.balance:
        raise ValueError("overdraft")
    account.balance -= amount
```

For type narrowing where the runtime condition is genuinely an
invariant (not a validation), prefer `typing.assert_never` /
`cast(...)` / a real exception, or suppress the line:

```python
assert value is not None  # assert-ok
```

## Why LLMs emit the bad shape

`assert cond, "msg"` is one expression; the safe `if not cond:
raise ...` shape is two statements with a longer total token
count. Token economy plus a sea of pre-PEP-8 tutorial code
means the unsafe shape is the autocomplete winner.
