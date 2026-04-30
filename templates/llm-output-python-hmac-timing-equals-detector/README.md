# llm-output-python-hmac-timing-equals-detector

Pure-stdlib python3 line scanner that flags timing-unsafe equality
comparison of secrets, HMACs, tokens, passwords, and digests in
LLM-emitted Python.

## Why

Python's `==` on `str` / `bytes` is a *short-circuit* byte-by-byte
compare — it returns False on the first mismatched byte, so the wall-
clock time it takes correlates with the length of the common prefix
between the two operands. A networked attacker that can measure
response time can recover an HMAC, API key, CSRF token, or password
one byte at a time.

LLMs emit this anti-pattern by reflex because:

1. `==` is the obvious / idiomatic equality operator in Python.
2. Most "verify HMAC" / "check API key" Stack Overflow answers from
   2010-2018 use plain `==`.
3. The model is optimising for "code that returns the right
   true / false", not for side-channel resistance.

The fix is `hmac.compare_digest(a, b)` (or `secrets.compare_digest`),
which is constant-time over equal-length inputs.

CWE references:
- **CWE-208**: Observable Timing Discrepancy.
- **CWE-203**: Observable Discrepancy.
- **CWE-1254**: Incorrect Comparison Logic Granularity.

## Usage

```sh
python3 detect.py path/to/auth.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any timing-unsafe comparison found, 0 otherwise.

## What it flags

`==` or `!=` on a line where one side references a secret-like
identifier (`token`, `api_key`, `secret`, `password`, `signature`,
`hmac`, `digest`, `csrf_token`, `nonce`, `otp`, `bearer`, `session_id`,
or any identifier containing those substrings) — including:

- `if expected_sig == provided_sig:`
- `bearer == expected_token`
- `submitted_password != stored_password`
- `csrf_token == session["csrf_token"]`

Plus any `==` / `!=` against the result of a hashing call:

- `hmac.new(key, msg, sha256).hexdigest() == provided_sig`
- `hashlib.sha256(payload).hexdigest() == expected_digest`
- `.digest()` variants of the same calls.

## What it does NOT flag

- `hmac.compare_digest(a, b)` and `secrets.compare_digest(a, b)` —
  the safe constant-time APIs.
- `==` against trivial literals (`None`, `True`, `False`, integers).
- Secret-named identifiers that only appear inside string literals
  or `#` comments.
- Lines suffixed with `# timing-safe-ok` (for unit-test fixtures
  where plaintext equality on a non-secret is intentional).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.py` case and is
silent on every `examples/good/*.py` case.

Worked example output:

```
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```
