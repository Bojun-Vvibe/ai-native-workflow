# llm-output-yaml-unsafe-load-detector

Pure-stdlib python3 single-pass scanner that flags **unsafe PyYAML
loader calls** in `*.py` files. The canonical YAML
deserialisation-RCE footgun.

## What it catches

PyYAML's `yaml.load(stream)` without an explicit safe Loader will
honour `!!python/object/apply:os.system` tags and execute arbitrary
code while parsing the document. PyYAML 5.1 added a deprecation
warning for the missing `Loader=` keyword, but the unsafe behaviour
is still available through `yaml.unsafe_load`, `yaml.Loader`,
`yaml.UnsafeLoader`, and `yaml.FullLoader` (which permits a *subset*
of Python tags including `!!python/name:`).

LLMs almost always emit `yaml.load(open("config.yaml"))` when asked
to "parse a YAML file" because that's the shortest snippet on Stack
Overflow circa 2014. This template's worked example exercises the
eight realistic shapes that produce CVE-grade behaviour.

The scanner emits one of these finding kinds:

- `yaml-load-no-loader` — `yaml.load(...)` with no `Loader=` kwarg
- `yaml-load-unsafe-loader` — `yaml.load(..., Loader=<unsafe>)`
- `yaml-load-all-no-loader` / `yaml-load-all-unsafe-loader`
- `yaml-unsafe-load`, `yaml-unsafe-load-all`
- `yaml-full-load`, `yaml-full-load-all`

`yaml.safe_load`, `yaml.safe_load_all`, and `yaml.load(s,
Loader=SafeLoader)` / `Loader=CSafeLoader` (with or without the
`yaml.` prefix) are **not** flagged. Suppress an audited line with
a trailing `# yaml-load-ok` comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight `.py` files, each demonstrating one
  unsafe call shape (`load`/`load_all` without Loader, with
  `Loader`/`FullLoader`/`UnsafeLoader`, and the always-unsafe
  `unsafe_load`/`unsafe_load_all`/`full_load` direct calls).
- `examples/good/` — five `.py` files (`safe_load`,
  explicit `SafeLoader`, `CSafeLoader`, docstring mention,
  suppressed line) that must **not** fire.
- `verify.sh` — runs `detect.py` against the corpora, asserts
  `bad >= 8`, `good == 0`, and exits 0 on PASS / 1 on FAIL.

## Usage

```sh
python3 detect.py path/to/project/
```

Exit code 1 if any findings, 0 otherwise. Output is one
`file:line:col: <kind> — <line>` per finding plus a trailing
`# N finding(s)` summary.

## Verification

```
$ ./verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

`bad=8/good=0 PASS`.

## Limitations

- Heuristic, line-oriented (with multi-line triple-quoted-string
  state carried across lines so docstrings are not scanned). A
  call argument that spans multiple physical lines is only
  inspected on the line where the call name appears — a multi-line
  `yaml.load(\n    s,\n    Loader=SafeLoader,\n)` may be
  conservatively flagged as `no-loader`. Reformat or add
  `# yaml-load-ok` after audit.
- Aliased imports (`import yaml as Y; Y.load(...)`) are not caught
  by the call-name match. The detector only matches the literal
  `yaml.` prefix.
- `ruamel.yaml`'s `YAML(typ="safe").load(...)` API is out of scope
  — that's a different surface and is safe by construction when
  `typ="safe"`.
- Loader kwarg detection is regex-based; an unusual Loader
  expression like `Loader=get_loader()` is treated as unsafe (no
  match for `SafeLoader`), which is the conservative default.
