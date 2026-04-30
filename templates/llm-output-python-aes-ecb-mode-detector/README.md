# llm-output-python-aes-ecb-mode-detector

Pure-stdlib python3 line scanner that flags use of ECB block-cipher
mode (AES, DES, 3DES, Blowfish) in LLM-emitted Python code.

## Why

ECB encrypts each block independently with the same key, so identical
plaintext blocks become identical ciphertext blocks. This leaks
structure (the canonical "ECB penguin" image), enables block
reordering / replay, and is forbidden by all modern crypto guidance.

LLMs reach for ECB as a reflex because it is the only AES mode that
takes no IV / nonce, and because most pre-2015 "AES in Python"
tutorials use it as the introductory example.

CWE references:
- **CWE-327**: Use of a Broken or Risky Cryptographic Algorithm.
- **CWE-696**: Incorrect Behavior Order.
- **CWE-1240**: Use of a Cryptographic Primitive with a Risky Implementation.

## Usage

```sh
python3 detect.py path/to/crypto.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any ECB usage found, 0 otherwise.

## What it flags

- `AES.new(key, AES.MODE_ECB)` / `DES.new(...)` / `DES3.new(...)` /
  `Blowfish.new(...)` (pycryptodome / pycrypto).
- Bare `MODE_ECB` references (`from Crypto.Cipher.AES import MODE_ECB`
  followed by `AES.new(key, MODE_ECB)`).
- `Cipher(algorithms.AES(key), modes.ECB())` (pyca/cryptography).
- `modes.ECB()` standalone calls.
- `Cipher(algorithms.AES(key), ECB())` after `from ... import ECB`.

## What it does NOT flag

- Safe modes: `MODE_CBC`, `MODE_CTR`, `MODE_GCM`, `MODE_OCB`,
  `modes.GCM(...)`, `modes.CTR(...)`, `modes.CBC(...)`.
- `AES-ECB` mentioned in a `#` comment or string literal.
- Import statements (`from Crypto.Cipher.AES import MODE_ECB`) on
  their own — only the actual use is flagged.
- Lines suffixed with `# aes-ecb-ok` (for FIPS KAT / test-vector
  fixtures where ECB is required by spec).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.py` case and is
silent on every `examples/good/*.py` case.
