# llm-output-django-allowed-hosts-wildcard-detector

Pure-stdlib python3 line scanner that flags wildcard `ALLOWED_HOSTS`
configurations in Django settings emitted by LLMs.

## Why

Django's `ALLOWED_HOSTS` is the framework defense against HTTP
Host-header injection. Setting it to `["*"]` disables that defense,
enabling password-reset poisoning, cache poisoning, and breaking
virtual-host isolation.

CWE references:
- **CWE-942**: Permissive Cross-domain Policy with Untrusted Domains.
- **CWE-20**: Improper Input Validation (Host header is input).

## Usage

```sh
python3 detect.py path/to/settings.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any wildcard `ALLOWED_HOSTS` finding, 0 otherwise.

## What it flags

- `ALLOWED_HOSTS = ["*"]` and tuple form.
- `ALLOWED_HOSTS = "*"` (bare-string form).
- `ALLOWED_HOSTS += ["*"]`, `.append("*")`, `.extend([..., "*"])`,
  `.insert(i, "*")`.
- Wildcard mixed into otherwise-restrictive lists
  (`["app.example.com", "*"]`).

## What it does NOT flag

- Explicit allowlists: `ALLOWED_HOSTS = ["app.example.com"]`.
- Empty list `ALLOWED_HOSTS = []` (Django default).
- Subdomain Django syntax `".example.com"` (restrictive, not permissive).
- Environment-driven values: `os.environ["HOSTS"].split(",")`.
- Lines with the trailing suppression marker `# allowed-hosts-ok`.
- Occurrences inside `#` comments or string literals.

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.py` case and is
silent on every `examples/good/*.py` case.
