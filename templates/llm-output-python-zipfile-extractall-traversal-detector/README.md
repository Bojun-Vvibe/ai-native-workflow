# llm-output-python-zipfile-extractall-traversal-detector

Pure-stdlib python3 line scanner that flags unsafe `ZipFile.extractall()`
("Zip Slip") and `shutil.unpack_archive()` calls in LLM-emitted
Python.

## Why

`zipfile.ZipFile(...).extractall(...)` happily writes any path encoded
in the archive — including absolute paths (`/etc/cron.d/evil`) and
traversal sequences (`../../etc/passwd`). An attacker who controls
the archive can overwrite arbitrary files on the host filesystem.
This is the "Zip Slip" class of bug (Snyk, 2018) and shows up almost
any time an LLM is asked "unzip this user upload".

LLMs reach for `extractall` by reflex because:

1. It is the one-liner answer to "extract this zip".
2. Most "Python unzip" Stack Overflow answers use it without any
   per-member path validation.
3. The model is optimising for "fewest lines that work on the happy
   path", not for adversarial input.

`shutil.unpack_archive(...)` is the same flaw with a different
import — it dispatches to `zipfile`/`tarfile` under the hood with no
member validation.

CWE references:
- **CWE-22**: Improper Limitation of a Pathname to a Restricted
  Directory ("Path Traversal").
- **CWE-23**: Relative Path Traversal.
- **CWE-73**: External Control of File Name or Path.

## Usage

```sh
python3 detect.py path/to/handler.py
python3 detect.py path/to/project/   # recurses *.py
```

Exit code 1 if any unsafe extraction found, 0 otherwise.

## What it flags

- `zipfile.ZipFile(arc).extractall(dest)` chained on one line.
- `from zipfile import ZipFile` followed by `z = ZipFile(arc)` and
  `z.extractall(...)`.
- `with zipfile.ZipFile(arc) as zf:` followed by `zf.extractall(dest)`.
- `shutil.unpack_archive(<arg>)` (always — same flaw, separate API).
- A bare `.extractall(` call when the file imports `zipfile` and does
  not define a safe-extract helper.

## What it does NOT flag

- Files that define a guard helper (`_safe_extract`, `safe_extract`,
  `_safe_unzip`, `safe_unzip`) anywhere in the file.
- Lines with an explicit `realpath(...).startswith(...)` or
  `Path(...).resolve().is_relative_to(...)` guard.
- `tarfile.extractall` — covered by the sibling
  `llm-output-tarfile-extractall-traversal-detector` template.
- `extractall` text inside docstrings, multi-line strings, or `#`
  comments.
- Lines suffixed with `# zipslip-ok`.

## Verify the worked example

```sh
bash verify.sh
```

Asserts the detector flags every `examples/bad/*.py` case and is
silent on every `examples/good/*.py` case.

Worked example output:

```
bad findings:  5 (rc=1)
good findings: 0 (rc=0)
PASS
```
