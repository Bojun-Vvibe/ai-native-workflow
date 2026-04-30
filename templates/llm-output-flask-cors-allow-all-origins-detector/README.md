# llm-output-flask-cors-allow-all-origins-detector

Single-pass python3 stdlib scanner for wildcard CORS configurations
in LLM-emitted Python web code. Catches the half-dozen ways an LLM
will tell you to "just allow all origins" — across Flask-CORS,
django-cors-headers, raw header sets, and Starlette / FastAPI
middleware.

## Why it exists

Cross-Origin Resource Sharing (CORS) lets a browser at origin A
talk to an HTTP API at origin B. The server controls who is
allowed via `Access-Control-Allow-Origin`. Setting that header
to `*` — especially while accepting credentialed requests —
turns every authenticated endpoint into a CSRF-amplifier: any
random page the user visits can read responses from your API as
that user.

LLMs reach for wildcard CORS reflexively because the shortest
recipe on the public internet is `CORS(app)` (Flask-CORS) or
`CORS_ORIGIN_ALLOW_ALL = True` (django-cors-headers), both of
which default to or explicitly allow `*`. Same story for
FastAPI / Starlette `CORSMiddleware(..., allow_origins=["*"])`.

The fix is almost always trivial — list the actual origins:

```python
CORS(app, origins=["https://app.example.com"])         # safe
CORS(app)                                              # wildcard
CORS(app, origins="*")                                 # wildcard
```

## What it flags

- `flask_cors.CORS(app)` with no `origins=` (defaults to `*`).
- `CORS(app, origins="*")` or `origins=["*"]`, including the
  per-resource `resources={...: {"origins": "*"}}` shape.
- `flask_cors.cross_origin()` with no `origins=` argument.
- `cross_origin(origins="*")` / `origins=["*"]`.
- Manual `response.headers["Access-Control-Allow-Origin"] = "*"`.
- `CORS_ORIGIN_ALLOW_ALL = True` (django-cors-headers, legacy).
- `CORS_ALLOW_ALL_ORIGINS = True` (django-cors-headers, modern).
- `CORS_ALLOWED_ORIGINS = ["*"]` (django-cors-headers, modern).
- `CORSMiddleware(..., allow_origins=["*"])` and the
  `app.add_middleware(CORSMiddleware, allow_origins=["*"])`
  shape used by FastAPI / Starlette.

## What it does NOT flag

- Explicit allowlists: `origins=["https://app.example.com"]`,
  `CORS_ALLOWED_ORIGINS = ["https://app.example.com"]`.
- `CORS(app, resources={...})` with non-wildcard per-resource
  origins.
- `CORS_ALLOW_ALL_ORIGINS = False` / `CORS_ORIGIN_ALLOW_ALL = False`.
- Lines marked with the trailing suppression marker
  `# cors-wildcard-ok`.
- Occurrences inside `#` comments or string literals (the scanner
  masks both before matching, so the docstring above doesn't
  self-flag).

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

Targets `*.py` files plus any file whose first line is a python shebang.

## Worked example

`examples/bad/` contains 11 wildcard shapes; `examples/good/`
contains 8 safe shapes plus the suppression marker. `verify.sh`
asserts `bad >= 11` and `good == 0`.

```
$ ./verify.sh
bad findings:  11 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/bad_cases.py:8:1: flask-cors-default-wildcard — CORS(app)
examples/bad/bad_cases.py:11:1: flask-cors-origins-wildcard — CORS(app, origins="*")
examples/bad/bad_cases.py:14:1: flask-cors-origins-wildcard — CORS(app, origins=["*"])
examples/bad/bad_cases.py:17:1: flask-cors-resources-wildcard — CORS(app, resources={r"/api/*": {"origins": "*"}})
examples/bad/bad_cases.py:22:2: flask-cross-origin-default-wildcard — @cross_origin()
examples/bad/bad_cases.py:29:2: flask-cross-origin-wildcard — @cross_origin(origins="*")
examples/bad/bad_cases.py:38:1: manual-allow-origin-wildcard — response.headers["Access-Control-Allow-Origin"] = "*"
examples/bad/bad_cases.py:43:1: django-cors-allow-all — CORS_ORIGIN_ALLOW_ALL = True
examples/bad/bad_cases.py:46:1: django-cors-allow-all — CORS_ALLOW_ALL_ORIGINS = True
examples/bad/bad_cases.py:49:1: django-cors-allowed-origins-wildcard — CORS_ALLOWED_ORIGINS = ["*"]
examples/bad/bad_cases.py:55:1: starlette-cors-allow-origins-wildcard — app.add_middleware(CORSMiddleware, allow_origins=["*"])
# 11 finding(s)
```

## Suppression

Add `# cors-wildcard-ok` at the end of any line you have audited.

## Layout

```
llm-output-flask-cors-allow-all-origins-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/bad_cases.py
    └── good/good_cases.py
```

## Limitations

- Single-line analysis. A `CORS(` whose call spans many lines
  isn't reassembled — extend with a parenthesis-aware multi-line
  buffer if your codebase formats long calls.
- Heuristic origin detection. A computed origin list assigned to
  `CORS_ALLOWED_ORIGINS` from a function call won't be inspected;
  the detector only sees `[ "*" ]` literally. Pair with a Django
  settings test that asserts the resolved list contains no `"*"`.
- No cross-file analysis.
