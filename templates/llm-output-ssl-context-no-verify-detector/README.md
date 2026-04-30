# llm-output-ssl-context-no-verify-detector

Defensive lint scanner that flags Python code which constructs an
`ssl.SSLContext` with TLS verification disabled.

## Problem

LLMs frequently emit `ssl._create_unverified_context()` or set
`ctx.check_hostname = False` / `ctx.verify_mode = ssl.CERT_NONE` to make a
self-signed-cert demo "just work". Once that pattern lands in real code, the
client trusts any certificate an attacker presents — full MITM with no
warning.

CWE-295 (Improper Certificate Validation) and the Python `ssl` module's own
documentation explicitly warn against `_create_unverified_context`. Some of
the worst-impact incidents (e.g. Lenovo Superfish, multiple banking-app CVEs)
are this exact bug.

## Why it matters

* Disables the entire TLS trust chain, silently.
* The names start with `_` so a casual reader assumes "this is internal, must
  be fine" — exactly the opposite of the truth.
* `ssl._create_default_https_context = ssl._create_unverified_context`
  poisons every subsequent `urllib.request.urlopen("https://...")` in the
  process.

## How to use

```bash
python3 detect.py path/to/src
echo $?   # 0 = clean, 1 = findings
```

The detector recurses directories looking for `*.py`, ignores comments and
string literals, and accepts an opt-out marker `# ssl-ok` on any line that
intentionally disables verification (e.g. inside a localhost-only test
fixture).

## Sample output

```
examples/bad/01_unverified_context.py:6: ssl-no-verify: ssl._create_unverified_context() :: ctx = ssl._create_unverified_context()
examples/bad/02_check_hostname_false.py:7: ssl-no-verify: check_hostname = False :: ctx.check_hostname = False
examples/bad/02_check_hostname_false.py:8: ssl-no-verify: verify_mode = CERT_NONE :: ctx.verify_mode = ssl.CERT_NONE
examples/bad/03_global_default.py:5: ssl-no-verify: global default HTTPS context disabled :: ssl._create_default_https_context = ssl._create_unverified_context
examples/bad/04_stdlib_context.py:5: ssl-no-verify: ssl._create_stdlib_context() :: ctx = ssl._create_stdlib_context()
```

## Run the worked example

```bash
bash verify.sh
```

`verify.sh` runs the detector over `examples/bad/` (must produce ≥4 findings,
exit 1) and over `examples/good/` (must produce 0 findings, exit 0).
