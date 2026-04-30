# llm-output-crypto-hardcoded-key-detector

Defensive lint scanner that flags Python source where a
cryptographic primitive is being constructed with a **literal**
key, secret, or seed baked directly into the file.

This is a *detector only*. It never generates keys, never
suggests "stronger" key material, and never rewrites code. Its
sole purpose is to catch the canonical LLM footgun where an
assistant, asked to "encrypt this string", emits something like:

```python
from cryptography.fernet import Fernet
f = Fernet(b"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
```

…which then gets committed and the secret leaks.

## What it flags

A literal `b"..."` / `"..."` in the **first positional slot** of:

- `Fernet(...)` (and qualified `cryptography.fernet.Fernet(...)`)
- `AES.new(...)`, `DES.new(...)`, `DES3.new(...)`,
  `Blowfish.new(...)`, `ChaCha20.new(...)`
- `ChaCha20Poly1305(...)`, `AESGCM(...)`, `AESCCM(...)`
- `algorithms.AES(...)`, `algorithms.ARC4(...)`
- `hmac.new(...)`, `hmac.HMAC(...)`, bare `HMAC(...)`

…and a literal in the **second positional slot** of:

- `jwt.encode(payload, key, ...)`

Common kwarg forms (`key=b"..."`, `Key="..."`) are also caught
when they appear in the first/second arg position.

## What it does NOT flag

- Calls where the key argument is a `Name` (variable),
  `Attribute`, or function `Call` — the assumption is the secret
  comes from `os.environ`, a keyring, KMS, or a vault.
- Lines marked with a trailing `# crypto-key-ok` comment
  (legacy fixtures tracked elsewhere).
- Occurrences inside `#` comments or string / docstring
  literals — the scrubber masks them before matching.

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
