# llm-output-template-injection-jinja-detector

Pure-stdlib python3 single-pass scanner that flags **server-side
template injection (SSTI)** in Python code that calls Jinja2's
`render_template_string`, `Environment.from_string`, or
`jinja2.Template` with a dynamically-built template body.

## What it catches

The Jinja2 sandbox is *not* enabled by default. When a Flask /
Quart / Sanic handler builds the template body from request data
(`request.args["x"]`, an f-string, `"a" + user`, `.format(...)`,
`%`, a method call) and passes it to `render_template_string`, the
attacker controls the entire template AST. The classic payload
`{{ ''.__class__.__mro__[1].__subclasses__() }}` walks to
`os.popen` and lands RCE — this is the SSTI footgun LLMs reproduce
when asked for "render a greeting with the user's name".

The scanner flags three call surfaces:

- `render_template_string(EXPR, ...)`
- `Environment().from_string(EXPR)`
- `jinja2.Template(EXPR)`

`Template` and `from_string` are only flagged if the file imports
`jinja2` (otherwise they're false positives — they're common names
in unrelated libraries).

A purely literal `render_template_string("Hello {{ name }}",
name=user)` is **not** flagged: the template is constant,
autoescaping protects HTML output, and the user input is just
context. Suppress an audited line with a trailing `# ssti-ok`
comment.

## Files

- `detect.py` — single-file python3 stdlib scanner (no deps).
- `examples/bad/` — eight `.py` files, each demonstrating one
  dynamic template-source shape that should fire (concat, f-string,
  `.format`, `%`, method call, bare name reference, `from_string`,
  `Template(...)`).
- `examples/good/` — five `.py` files (literal template body,
  docstring-only mention, suppressed line, file-backed
  `render_template`, unrelated `Template` class) that must **not**
  fire.
- `verify.sh` — runs `detect.py` against the corpora, asserts
  `bad >= 8`, `good == 0`, and exits 0 on PASS / 1 on FAIL.

## Usage

```sh
python3 detect.py path/to/app/
```

Exit code 1 if any findings, 0 otherwise. Output is one
`file:line:col: jinja-ssti-dynamic-template — <line>` per finding
plus a trailing `# N finding(s)` summary.

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
  call whose first argument spans multiple physical lines will
  only see what fits on the line of the call name.
- Does not statically prove that the dynamic source is
  attacker-controlled — it only flags the dynamic surface. Triage
  each finding against the source of the variable; suppress with
  `# ssti-ok` once audited.
- Aliased imports (`from flask import render_template_string as
  rts`) are not caught by the call-name match. Flag the import in
  review or rely on `Template` / `from_string` matches plus the
  `jinja2`-import gate.
- The literal-arg test recognises ordinary string literals (`"..."`,
  `'...'`, triple-quoted, `r"..."`, `b"..."`); f-strings always
  count as dynamic.
