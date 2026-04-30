# llm-output-weak-random-for-secrets-detector

Defensive lint detector that flags Python's `random` module
being used to mint **security-sensitive values** — session
tokens, API keys, password-reset codes, CSRF tokens, salts,
IVs, OTPs — when an LLM-generated snippet should have used
`secrets` or `os.urandom` instead.

## Why this exists

`random` is a Mersenne Twister PRNG. Once an attacker observes
~624 outputs they can fully reconstruct the internal state and
predict every future value. LLMs love to emit:

```python
import random, string
token = "".join(random.choice(string.ascii_letters) for _ in range(32))
```

…because that's the top Stack Overflow answer for "generate a
random string in Python". The hardened replacement is
`secrets.token_urlsafe(32)`. This detector audits a tree of
`*.py` files and flags every weak-random call whose context
mentions a security identifier so reviewers can swap the
import.

## What is flagged

| Pattern                                                              | Kind                                  |
|----------------------------------------------------------------------|---------------------------------------|
| `random.<call>(...)` near a security identifier                      | `weak-random-<call>-for-secret`       |
| Bare-imported call (`from random import choice` then `choice(...)`)  | `weak-random-bare-<call>-for-secret`  |
| `random.Random()` (the non-CSPRNG class) near a security identifier  | `weak-random-Random-class-for-secret` |

`<call>` ∈ `random`, `randint`, `randrange`, `choice`,
`choices`, `sample`, `shuffle`, `getrandbits`, `uniform`,
`randbytes`.

A "security identifier" is any of: `token`, `secret`,
`password`, `passwd`, `apikey`, `api_key`, `nonce`, `salt`,
`iv`, `session`, `csrf`, `xsrf`, `otp`, `mfa`, `reset_code`,
`auth`, `signature`, `signing_key`, `cookie`, `jwt`, `bearer`
— matched case-insensitively in the same line ±2 lines of
context.

## What is NOT flagged

* `secrets.*`, `os.urandom`, `random.SystemRandom().*` — these
  are CSPRNGs.
* `random.*` calls in non-security contexts (Monte Carlo,
  shuffling decks, picking demo words, chart colours).
* Lines marked with a trailing `# weak-random-ok` comment.
* Occurrences inside `#` comments or string literals.

## Usage

```sh
python3 detect.py path/to/code [more/paths ...]
```

Exit code `1` if any findings, `0` otherwise. python3 stdlib
only — no external deps.

## Sample output

```
examples/bad/secrets.py:7:39: weak-random-choice-for-secret — return "".join(random.choice(string.ascii_letters) for _ in range(32))
examples/bad/secrets.py:11:30: weak-random-choices-for-secret — return "".join(random.choices(string.ascii_letters, k=12))
examples/bad/secrets.py:15:19: weak-random-getrandbits-for-secret — return random.getrandbits(128)
examples/bad/secrets.py:23:19: weak-random-randrange-for-secret — return random.randrange(100000, 999999)
examples/bad/secrets.py:27:12: weak-random-bare-randint-for-secret — return randint(100000, 999999)
# 11 finding(s)
```

## Worked example

```sh
bash verify.sh
# bad findings:  11 (rc=1)
# good findings: 0 (rc=0)
# PASS
```

## Suppression

Append `# weak-random-ok` to a line that has been audited as
intentionally non-cryptographic (e.g. seeded fixtures,
reproducible-test scaffolding). Reviewers should require an
adjacent comment justifying every suppression.

## Limitations

* Regex-based — does not perform full AST or data-flow
  analysis. Will miss weak random whose output flows into a
  security identifier across function boundaries with no
  in-context naming hint.
* The "security context" radius is 2 lines either side of the
  call; longer-range data flows will be missed. This is by
  design to keep precision high.
* Only inspects `*.py` files (and `python` shebang scripts).
* `random.SystemRandom().<call>(...)` is intentionally not
  flagged even in security contexts — it is a CSPRNG wrapper
  around `os.urandom`.
