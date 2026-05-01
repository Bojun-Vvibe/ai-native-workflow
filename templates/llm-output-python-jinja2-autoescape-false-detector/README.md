# llm-output-python-jinja2-autoescape-false-detector

Stdlib-only Python detector that flags Jinja2 rendering surfaces
constructed with **HTML autoescaping disabled**. This is the canonical
CWE-79 (XSS) shape that LLMs love to emit when asked "set up Jinja for
my Flask app": the model copies the *library default* (`autoescape=False`)
into the explicit constructor call, which silently turns every future
`{{ user_html }}` interpolation into a stored / reflected XSS sink.

This is **distinct** from
`llm-output-template-injection-jinja-detector`, which flags
**template-source** injection (SSTI, CWE-94). Here we focus on the
much more common everyday hazard: a correctly-bounded template body,
but with autoescape switched off.

## Why "autoescape" is the right anchor

Jinja2's library default is `autoescape=False` for backward
compatibility with its pre-Flask history. Flask's `render_template`
helper layers an HTML autoescape default on top, but as soon as a
project builds a custom `jinja2.Environment` for non-Flask delivery
(emails, static-site generation, server-rendered React shells,
admin dashboards, custom CMS), the library default leaks through.
Detecting the constructor call is the most reliable single anchor
because it survives renames, re-imports, and helper wrappers.

## Heuristic

A finding is emitted when **the file references `jinja2`** AND one of:

1. `jinja2.Environment(...)` / `Environment(...)` with
   `autoescape=False`, `autoescape=0`, `autoescape=None`,
   `autoescape=select_autoescape([])`, `autoescape=select_autoescape()`,
   or `autoescape=lambda *_: False`.
2. The same `Environment(...)` call with **no `autoescape=` keyword
   at all** when the call site (or its 200-char preceding context)
   shows an HTML cue: `FileSystemLoader(`, `PackageLoader(`,
   `DictLoader(`, `ChoiceLoader(`, or a string ending in `.html`,
   `.htm`, `.j2`, or `.jinja`.
3. `jinja2.Template(<source>, autoescape=False)` (and the other
   falsey forms above).

The detector does **not** flag:

- `Environment(autoescape=True)` (correct).
- `Environment(autoescape=select_autoescape(['html', 'htm']))`
  (the standard recommended idiom).
- `Environment(autoescape=select_autoescape(default_for_string=True, default=True))`.
- `Template("...")` with no `autoescape=` kwarg — non-HTML uses of
  `Template` (e.g. SQL fragment generation) are legitimately
  autoescape-off.
- Files that never reference `jinja2`, even if they have an
  `Environment(...)` call (avoids false positives on Django,
  SQLAlchemy, etc.).

The kwarg-value extractor is paren / bracket / string aware so
`autoescape=select_autoescape(["html", "htm"])` is read as a single
value rather than truncated at the first comma.

## CWE / standards

- **CWE-79**: Improper Neutralization of Input During Web Page
  Generation ("Cross-site Scripting").
- **CWE-1336**: Improper Neutralization of Special Elements Used in a
  Template Engine (parent).
- **OWASP A03:2021** — Injection.

## Limits / known false negatives

- We don't follow autoescape settings that are computed at runtime
  (e.g. `ae = read_setting("autoescape"); Environment(autoescape=ae)`).
- We don't trace `env.autoescape = False` mutations after construction.
- A Flask app that uses **only** `flask.render_template` (not a
  custom Environment) is safe by default and we don't need to flag it.

## Usage

```bash
python3 detect.py path/to/file.py
python3 detect.py path/to/dir/   # walks *.py and *.py.txt
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_explicit_false.py         # autoescape=False
  02_missing_autoescape.py     # no autoescape= on HTML loader
  03_select_autoescape_empty.py # select_autoescape([])
  04_lambda_false.py           # autoescape=lambda name: False
  05_template_false.py         # Template(..., autoescape=False)
  06_zero_value.py             # autoescape=0
examples/good/
  01_explicit_true.py             # autoescape=True
  02_select_autoescape_html.py    # select_autoescape(["html","htm"])
  03_default_for_string.py        # default_for_string=True
  04_template_no_kwarg.py         # Template(...) without kwarg, non-HTML
  05_unrelated_environment.py     # different Environment class
  06_package_loader_true.py       # PackageLoader + autoescape=True
```
