# llm-output-hashlib-md5-sha1-detector

Defensive lint scanner that flags Python source where MD5 or
SHA-1 are used via `hashlib`. Both are broken for security
contexts (collision resistance, password storage, signature
digests, HMAC key derivation) and have been for years, yet LLMs
asked to "hash this password" or "fingerprint this token"
routinely emit them.

This is a *detector only*. It never modifies code and never
recomputes digests. Its sole purpose is to catch the canonical
LLM footgun where an assistant emits something like:

```python
import hashlib
fingerprint = hashlib.md5(token.encode()).hexdigest()
```

…or:

```python
from hashlib import sha1
pw_hash = sha1(password.encode()).hexdigest()
```

For non-security uses (cache-key bucketing, fixture identity,
non-cryptographic dedup) suppress the line with a trailing
`# weak-hash-ok` comment so the intent is documented.

## What it flags

- `hashlib.md5(...)` and `hashlib.sha1(...)`
- `hashlib.new("md5", ...)` / `hashlib.new("sha1", ...)`
  (case-insensitive, `MD-5` / `sha_1` tolerated)
- Bare `md5(...)` / `sha1(...)` calls when preceded by
  `from hashlib import md5` / `from hashlib import sha1`
  (including `from hashlib import md5 as hasher`)

## What it does NOT flag

- `hashlib.sha256(...)`, `sha384`, `sha512`, `blake2b`, `blake2s`
- Lines with a trailing `# weak-hash-ok` comment
- Occurrences inside `#` comments or string / docstring literals
- Attribute calls on unrelated objects (`obj.md5(...)`)

## Layout

```
.
├── README.md           # this file
├── detect.py           # python3 stdlib single-pass scanner
├── verify.sh           # end-to-end check (bad>=8, good==0)
└── examples/
    ├── bad/            # fixtures that MUST be flagged
    └── good/           # fixtures that MUST NOT be flagged
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
