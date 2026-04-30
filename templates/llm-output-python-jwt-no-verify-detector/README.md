# llm-output-python-jwt-no-verify-detector

Pure-stdlib `python3` line scanner that flags Python source where a
PyJWT call disables signature verification, asks for the `none`
algorithm, or relaxes the audience / expiry / issuer checks via the
`options` dict. All three are canonical "just decode this token"
LLM footguns: the resulting code accepts forged tokens.

This is a **detector only**. It never executes input, never emits
tokens, and never modifies code. It reads source files line by line
and prints findings.

## What it flags

- `verify=False` (PyJWT < 2.x kwarg) anywhere in a `jwt.decode(...)`
  / `jwt.encode(...)` call
- `options={"verify_signature": False, ...}`
- `options={"verify_aud": False, ...}`, `verify_exp`, `verify_iat`,
  `verify_nbf`, `verify_iss` set to `False`
- `algorithm="none"` (case-insensitive)
- `algorithms=["none"]`, `algorithms=["HS256", "none"]` (any list
  element that says `none`, case-insensitive)
- `algorithms=None` (PyJWT treats this as "no allow-list")

## What it does NOT flag

- `jwt.decode(token, key, algorithms=["HS256"])` — explicit allow-list
- `jwt.decode(..., options={"verify_signature": True})`
- Lines marked with a trailing `# jwt-verify-ok` comment
- Pattern occurrences inside multi-line triple-quoted docstrings
  (best-effort heuristic; single-line `"""..."""` docstrings that
  literally embed the footgun pattern will still be flagged)

## Layout

```
.
├── README.md                 # this file
├── detector.py               # python3 stdlib single-pass scanner
├── bad/                      # 6 fixtures that MUST be flagged
└── good/                     # 3 fixtures that MUST NOT be flagged
```

## Usage

```bash
python3 detector.py path/to/file_or_dir [more paths ...]
```

Exit codes:

- `0` — no findings
- `1` — one or more findings
- `2` — usage error

## Verified output

Run from the template root:

```text
$ python3 detector.py bad/
bad/04_algorithms_none_keyword.py:1: algorithms=None disables algorithm allow-list: """Bad fixture: algorithms=None bypasses allow-list."""
bad/04_algorithms_none_keyword.py:6: algorithms=None disables algorithm allow-list: return jwt.decode(token, key, algorithms=None)
bad/03_algorithms_none_in_list.py:6: algorithms list contains "none": return jwt.decode(token, "anything", algorithms=["HS256", "none"])
bad/05_algorithm_none_singular.py:1: algorithm="none" passed to jwt call: """Bad fixture: algorithm='none' (singular kwarg)."""
bad/05_algorithm_none_singular.py:6: algorithm="none" passed to jwt call: return jwt.encode(payload, key="", algorithm="None")
bad/06_options_verify_aud_exp_false.py:10: options dict disables verify_aud / verify_exp / verify_iat / verify_nbf / verify_iss:         options={"verify_aud": False, "verify_exp": False},
bad/01_verify_false.py:1: verify=False kwarg passed to jwt decode/encode: """Bad fixture: PyJWT decode with verify=False (PyJWT < 2.x footgun)."""
bad/01_verify_false.py:7: verify=False kwarg passed to jwt decode/encode:     return jwt.decode(token, key, verify=False)
bad/02_options_verify_signature_false.py:10: options dict disables verify_signature:         options={"verify_signature": False},
$ echo $?
1

$ python3 detector.py good/
$ echo $?
0
```

All 6 bad fixtures flagged at the line of the offense (with bonus
flags on bad-fixture docstrings whose text itself names the
footgun). All 3 good fixtures pass clean.

## Why this matters

A signed JWT only protects you if you actually verify the signature.
Calls like `jwt.decode(token, key, verify=False)` or
`algorithms=["none"]` reduce a JWT to base64-encoded JSON: any
attacker who can supply a token can supply any payload. LLMs love
suggesting these flags when the user complains the call "doesn't
work" — usually because the key or algorithm was wrong. This
detector keeps that reflex from landing in a pull request.
