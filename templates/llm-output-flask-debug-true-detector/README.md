# llm-output-flask-debug-true-detector

Single-pass python3 stdlib scanner for Flask apps shipped with debug
mode enabled. Flags `app.run(debug=True)`, `app.config["DEBUG"] = True`,
`app.config.update(DEBUG=True)`, and the matching `FLASK_DEBUG=1` /
`FLASK_ENV=development` environment shapes — both in Python source and
in Dockerfile / `.env` files.

## Why it exists

Flask's debug mode wires the Werkzeug interactive debugger into the
WSGI stack. When an unhandled exception fires, the debugger serves an
HTML page that lets anyone with a browser execute arbitrary Python in
the app's process — pinned only by a PIN that is derived from
predictable host facts and has been bypassed multiple times in the
wild. Running a debug-mode Flask app on a reachable interface is
equivalent to publishing a remote-code-execution endpoint.

LLMs reach for `app.run(debug=True)` because it is the canonical "hello
world" snippet in every Flask tutorial. The same shape leaks into
Dockerfiles (`ENV FLASK_DEBUG=1`) and into `os.environ` mutations
inside `if __name__ == "__main__":` blocks.

## What it flags

In `*.py` files (and python shebang files):

- `<app>.run(..., debug=True)` where `<app>` is one of `app`,
  `application`, `server`, `flask_app`, `wsgi`, `api`, `web`,
  `create_app`, or `Flask`.
- `<app>.config["DEBUG"] = True` (single or double quotes).
- `<app>.config.update(DEBUG=True, ...)`.
- `os.environ["FLASK_DEBUG"] = "1" | "true" | "True" | "yes" | "on"`.
- `os.environ["FLASK_ENV"] = "development"`.

In `Dockerfile`, `Dockerfile.*`, `.env`, `.env.*`, `.envrc`, `*.env`:

- `FLASK_DEBUG=1 | true | yes | on` (with optional `ENV ` or `export `
  prefix).
- `FLASK_ENV=development` (with optional `ENV ` or `export ` prefix).

## What it does NOT flag

- `app.run()` (default `debug=False`), `app.run(debug=False)`.
- `app.config["DEBUG"] = False`, `app.config.update(DEBUG=False)`.
- `FLASK_DEBUG=0`, `FLASK_ENV=production`.
- Lines marked with a trailing `# flask-debug-ok` comment.
- Patterns that appear inside `#` comments or triple-quoted docstrings.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 8 dangerous shapes; `examples/good/` has 8 safe
shapes plus a suppression marker and a docstring/comment containing
the literal patterns (which must NOT be flagged thanks to comment +
triple-quote masking).

```
$ ./verify.sh
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/bad_app.py:9:1: flask-app-run-debug-true — app.run(debug=True)
examples/bad/bad_app.py:12:1: flask-app-run-debug-true — app.run(host="0.0.0.0", port=5000, debug=True)
examples/bad/bad_app.py:15:1: flask-api-run-debug-true — api.run(debug=True)
examples/bad/bad_app.py:18:4: flask-config-debug-true — app.config["DEBUG"] = True
examples/bad/bad_app.py:21:4: flask-config-update-debug-true — app.config.update(DEBUG=True, TESTING=False)
examples/bad/bad_app.py:24:1: flask-env-flask-debug-true — os.environ["FLASK_DEBUG"] = "1"
examples/bad/bad_app.py:27:1: flask-env-flask-debug-true — os.environ["FLASK_DEBUG"] = "true"
examples/bad/bad_app.py:30:1: flask-env-flask-env-development — os.environ["FLASK_ENV"] = "development"
# 8 finding(s)
```

## Suppression

Add `# flask-debug-ok` at the end of any line you have audited (e.g. a
local-only dev entrypoint guarded by argv parsing).

## Layout

```
llm-output-flask-debug-true-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/bad_app.py
    └── good/good_app.py
```

## Notes on string-literal masking

The Python scanner uses two masked views per line:

- A "code only" view that masks comments and triple-quoted string
  contents but preserves single-line string literal text — this is
  needed so `os.environ["FLASK_DEBUG"] = "1"` matches against the
  `"FLASK_DEBUG"` and `"1"` literals.
- A fully-scrubbed view that masks all string contents — used for the
  `.run(..., debug=True)` call-shape detection where matching against
  literals is irrelevant.

The triple-quoted-state masking is what keeps the scanner's own
docstring (and similar docstrings in target files) from self-flagging.

## Limitations

- Single-line analysis. A `.run(` call split across many lines isn't
  reassembled; reformat to one line or extend with a paren-aware
  multi-line buffer.
- Heuristic name list for the `.run(debug=True)` shape — extend
  `APP_NAME_HINT` if your codebase uses other handle names.
- No dataflow. `os.environ.update({"FLASK_DEBUG": "1"})` is not
  matched; add a pattern if you need it.
