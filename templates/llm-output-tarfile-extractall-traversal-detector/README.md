# llm-output-tarfile-extractall-traversal-detector

Pure-stdlib python3 single-pass scanner that flags **unsafe archive
extraction** in `*.py` files. Catches the canonical CVE-2007-4559 /
"Zip Slip" footgun where a hostile archive member named
`../../etc/cron.hourly/payload` becomes an arbitrary-write
primitive on the host.

## What it catches

Python's `tarfile.TarFile.extractall()` and `extract()` honour any
absolute paths or `..` segments embedded in member names. Python
3.12 added a `filter=` parameter precisely so callers could opt
into the safe `"data"` filter; PEP 706 will eventually flip the
default but is not there yet on every supported runtime, so the
scanner requires the kwarg to be present and set to a known-safe
value.

`zipfile.ZipFile.extractall()` / `.extract()` will *not* honour
`..` in member names on modern CPython, but they will still
silently truncate leading slashes, traverse symlink members on
Unix, and write through any pre-existing symlinks in the
destination tree — so they are always flagged.

`shutil.unpack_archive()` is always flagged because it dispatches
to the same vulnerable backends.

The scanner emits one of these finding kinds:

- `tar-extractall-no-safe-filter` / `tar-extract-no-safe-filter`
- `zip-extractall` / `zip-extract`
- `shutil-unpack-archive`

Lines marked with a trailing `# extractall-ok` comment are
suppressed. Calls inside string literals and `#` comments are
ignored.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — six `.py` files exercising the three
  flagged surfaces (tar without filter, zip extractall, shutil
  unpack).
- `examples/good/` — four `.py` files showing the safe shapes
  (tarfile `filter="data"`, `filter=tarfile.data_filter`,
  audited-and-suppressed, docstring mention).
- `verify.sh` — runs the detector against `bad/` and `good/`
  and asserts the expected counts and exit codes.

## Run

```bash
bash verify.sh
```

Expected: `PASS`, with at least 6 findings against `bad/` and 0
against `good/`.

## Safe replacement patterns

```python
# Python >= 3.12, the only fully safe shape:
with tarfile.open(path) as tar:
    tar.extractall(dest, filter="data")

# Equivalent with the callable form:
tar.extractall(dest, filter=tarfile.data_filter)

# For zip archives, validate every member before extraction:
with zipfile.ZipFile(path) as zf:
    base = os.path.realpath(dest)
    for name in zf.namelist():
        target = os.path.realpath(os.path.join(dest, name))
        if not target.startswith(base + os.sep):
            raise RuntimeError(f"unsafe member: {name}")
        zf.extract(name, dest)  # extractall-ok
```

## Why LLMs emit the bad shape

"Extract a tar.gz" autocompletes to `tarfile.open(p).extractall(d)`
on the back of a decade of Stack Overflow answers written before
PEP 706. The unsafe shape is shorter, so it wins token economy.
