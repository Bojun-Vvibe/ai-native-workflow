# llm-output-python-yaml-load-detector

Static detector for the Python `yaml.load(...)` anti-pattern: calling
PyYAML's loader without a safe `Loader=` keyword. Loading untrusted
YAML through the default loader can execute arbitrary Python via
`!!python/object/apply:` and similar tags — the textbook CWE-502
shape.

Why an LLM emits this: PyYAML's pre-5.1 docs and a decade of Stack
Overflow answers used `yaml.load(f)` as the canonical example. PyYAML
finally added a runtime warning, then made the call require a
`Loader=` argument — but the warning is silenced everywhere and
`Loader=yaml.FullLoader` (the documented "fix") is *also* unsafe for
attacker-controlled input. The reflex pattern keeps showing up.

## What this flags

A finding is emitted whenever a call shaped like
`<id>.load(...)` or `<id>.load_all(...)` appears, where `<id>` is
`yaml`, `yml`, `y`, or any identifier ending in `yaml`
(case-insensitive — covers `import yaml as myyaml`), and the
argument list does **not** contain any of:

* `SafeLoader`
* `CSafeLoader`
* `BaseLoader`
* `CBaseLoader`
* `safe_load`

`Loader=yaml.FullLoader` and `Loader=yaml.Loader` are intentionally
**still flagged** — both deserialize unsafe tags.

Suppress with `# llm-allow:python-yaml-load-unsafe` on the same
logical line as the call.

Python `#` comments and string literal interiors (including triple-
quoted strings and docstrings) are masked before scanning, so
example snippets in docstrings don't fire. Fenced ` ```python ` code
blocks in Markdown / RST are also extracted and scanned.

## CWE references

* **CWE-502**: Deserialization of Untrusted Data.
* **CWE-20**: Improper Input Validation.
* **CWE-94**: Improper Control of Generation of Code ('Code
  Injection').

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. Python 3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

The fixtures in `examples/bad/loader.py` exercise eight unsafe
shapes (bare load, load_all, FullLoader, explicit `yaml.Loader`,
two import aliases, file-handle form, multi-line form) and the
detector flags all eight. The fixtures in `examples/good/loader.py`
exercise `safe_load`, explicit `SafeLoader` / `CSafeLoader` /
`BaseLoader`, aliased safe loader, bare `SafeLoader`, suppressed
legacy line, comment-only mention, string-literal mention, and
unrelated `json.load` — zero of them fire.

## Limitations

* Heuristic only — not an AST analyzer. A `Loader=` value that
  *contains* the substring `SafeLoader` but is actually a custom
  unsafe class will be missed.
* The `<id>` allowlist is conservative; `from yaml import load`
  and a bare `load(stream)` call will not be flagged. Importing
  the function this way is uncommon in LLM-generated code; if you
  see it, prefer the qualified form.
* No interprocedural taint tracking — the detector flags the call
  shape regardless of whether the input is actually attacker
  controlled.
