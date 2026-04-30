# llm-output-jwt-none-alg-detector

Defensive lint scanner that flags Python source where a JWT
`decode` call disables signature verification or accepts the
`none` algorithm. Both reduce a signed token to a plain JSON
blob that any caller can forge.

This is a *detector only*. It never emits tokens, never modifies
code, and never bypasses verification. Its sole purpose is to
catch the canonical LLM footgun where an assistant, asked to
"just decode this JWT", emits something like:

```python
import jwt
data = jwt.decode(token, key, verify=False)
```

…or:

```python
data = jwt.decode(token, key, algorithms=["none"])
```

…both of which trust user-supplied content as if it were signed.

## What it flags

- `verify=False` (PyJWT < 2.0 API) anywhere in a `decode(...)` call
- `options={"verify_signature": False, ...}`
- `algorithm="none"` / `algorithm="NONE"` (case-insensitive)
- `algorithms=["none"]` and `algorithms=["HS256", "none"]`
  (any list element that says `none`)
- `algorithms=None` (PyJWT treats as "no algorithm check")
- Bare `decode(...)` calls (e.g. after `from jwt import decode`)
  with any of the above patterns

## What it does NOT flag

- `jwt.decode(token, key, algorithms=["HS256"])` — explicit
  allow-list
- `jwt.decode(..., options={"verify_signature": True})`
- Lines marked with a trailing `# jwt-decode-ok` comment
- Occurrences inside `#` comments or string / docstring literals

## Layout

```
.
├── README.md           # this file
├── detect.py           # python3 stdlib single-pass scanner
├── verify.sh           # end-to-end check (bad>=8, good==0)
└── examples/
    ├── bad/            # 8 fixtures that MUST be flagged
    └── good/           # 3 fixtures that MUST NOT be flagged
```

## Usage

```bash
python3 detect.py path/to/file_or_dir
./verify.sh   # runs detector on examples/ and asserts counts
```

Exit codes:

- `0` — no findings (or `verify.sh` PASS)
- `1` — findings present (or `verify.sh` FAIL)
- `2` — usage error
