# llm-output-python-yaml-load-unsafe-detector

Pure-stdlib python3 line scanner that flags unsafe ``yaml.load`` usage
in LLM-emitted Python code.

## Why

PyYAML's default loader (and the explicit ``Loader=yaml.Loader`` /
``yaml.UnsafeLoader`` / ``yaml.FullLoader``) constructs arbitrary
Python objects from a YAML stream. A document like
``!!python/object/apply:os.system ["rm -rf /"]`` deserialises into a
side-effecting call. When the YAML input is attacker-influenced
(config from disk, network payload, file upload), this is arbitrary
code execution.

LLMs emit ``yaml.load(stream)`` by reflex because it is the shortest
"load YAML" snippet and matches pre-2019 PyYAML tutorials, and because
``safe_load`` requires the model to know the safe API exists.

CWE references:

- **CWE-502**: Deserialization of Untrusted Data.
- **CWE-94**:  Improper Control of Generation of Code ('Code Injection').
- **CWE-20**:  Improper Input Validation.

## Usage

```sh
python3 detect.py path/to/loader.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any unsafe usage found, 0 otherwise.

## What it flags

- ``yaml.load(stream)``                       — no Loader, pre-5.1 default unsafe.
- ``yaml.load(stream, Loader=yaml.Loader)``   — explicit unsafe Loader.
- ``yaml.load(stream, Loader=yaml.UnsafeLoader)``
- ``yaml.load(stream, Loader=yaml.FullLoader)`` — FullLoader still
  permits ``!!python/object/new`` constructors that can call arbitrary
  classes (CVE-2020-14343).
- ``yaml.load_all(stream[, Loader=...])``    — same risk, multi-doc.
- ``yaml.unsafe_load(stream)`` / ``yaml.unsafe_load_all(stream)``.

## What it does NOT flag

- ``yaml.safe_load(...)`` / ``yaml.safe_load_all(...)``.
- ``yaml.load(stream, Loader=yaml.SafeLoader)`` /
  ``yaml.load(stream, Loader=yaml.CSafeLoader)``.
- ``yaml.load`` mentioned inside a ``#`` comment or a string literal.
- Lines suffixed with ``# yaml-unsafe-ok`` (for trusted in-process
  round-trip of internally generated data).

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every ``examples/bad/*.py`` case and is
silent on every ``examples/good/*.py`` case.
