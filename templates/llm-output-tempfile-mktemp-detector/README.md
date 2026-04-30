# llm-output-tempfile-mktemp-detector

Defensive lint scanner that flags Python source where
`tempfile.mktemp()` is used. `mktemp` returns a path that does
not yet exist; the caller is expected to create the file. That
gap allows another process on the same filesystem to race the
caller — typically by symlinking the predicted path to an
attacker-chosen target before the caller opens it. Python's
docs have carried a deprecation note for years; the safe
primitives are `tempfile.mkstemp()` and the context managers
`NamedTemporaryFile`, `TemporaryFile`, `SpooledTemporaryFile`,
`TemporaryDirectory`.

LLMs asked to "give me a temp file path" routinely emit
`tempfile.mktemp()` because the name reads as the obvious
counterpart to `mkdir`. This detector exists to catch that.

This is a *detector only*. It never modifies code and never
creates temp files. Its sole purpose is to surface the call site
so a human can rewrite to `mkstemp` or a context manager.

## What it flags

- `tempfile.mktemp(...)` (with or without arguments)
- Bare `mktemp(...)` calls when preceded by
  `from tempfile import mktemp` (and aliased forms such as
  `from tempfile import mktemp as mk`)

## What it does NOT flag

- `tempfile.mkstemp(...)`, `mkdtemp`, `NamedTemporaryFile`,
  `TemporaryFile`, `SpooledTemporaryFile`, `TemporaryDirectory`
- Lines with a trailing `# mktemp-ok` comment
- Occurrences inside `#` comments or string / docstring literals
- Attribute calls on unrelated objects (`obj.mktemp(...)`)

## Layout

```
.
├── README.md           # this file
├── detect.py           # python3 stdlib single-pass scanner
├── verify.sh           # end-to-end check (bad>=5, good==0)
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
