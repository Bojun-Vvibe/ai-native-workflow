# llm-output-cors-wildcard-with-credentials-detector

Detect the broken-and-dangerous CORS combo where an LLM-emitted server
sets `Access-Control-Allow-Origin: *` together with
`Access-Control-Allow-Credentials: true`.

## Why

Per the Fetch spec, browsers reject any cross-origin response that
combines a wildcard `Allow-Origin` with credentials — so the code
either:

1. Doesn't actually work for credentialed XHR/fetch (silent breakage), or
2. Hints that a developer copied a "make CORS go away" snippet and will
   later swap the wildcard for an unsafe `Origin`-reflection that *does*
   ship cookies / `Authorization` headers to attacker-controlled origins.

LLMs reproduce this antipattern constantly (Express, Flask, FastAPI,
Spring, raw nginx/Apache config, plain `Set-Header`, etc.). Catching it
in generated output is a high-signal, framework-agnostic check.

## What it flags

A file (text/code/config) where, within a sliding 12-line window, the
detector sees BOTH:

- a wildcard origin: `Access-Control-Allow-Origin: *`, or a code-level
  equivalent (e.g. `res.setHeader("Access-Control-Allow-Origin", "*")`,
  `add_header Access-Control-Allow-Origin *`,
  `Header set Access-Control-Allow-Origin "*"`,
  `response.headers["Access-Control-Allow-Origin"] = "*"`,
  `Access-Control-Allow-Origin", "*"` in any quoting style), AND
- credentials enabled: `Access-Control-Allow-Credentials: true`, or a
  code-level equivalent (same shapes, value `true` / `"true"` /
  `True`).

Also flags single-call shorthands that bake both in at once:

- `cors({ origin: "*", credentials: true })` (Express `cors`)
- `CORSMiddleware(allow_origins=["*"], allow_credentials=True)` (FastAPI/Starlette)
- `CORS(app, origins="*", supports_credentials=True)` (Flask-CORS)
- `app.use(cors({origin: true, credentials: true}))` where
  `origin: true` reflects every origin (equivalent risk).

## What it does NOT flag

- Wildcard origin alone (no credentials) — that's standard public-API CORS.
- Credentials alone with a specific origin — the safe shape.
- Lines suffixed with `# cors-ok` or `// cors-ok`.
- Matches inside `#` / `//` comments or inside string literals that
  obviously document the antipattern (`"do not do: ..."` heuristic via
  the `cors-ok` suppressor).

## Usage

```bash
python3 detect.py path/to/dir
```

Exit 1 on findings, 0 otherwise. Pure python3 stdlib. Walks any file
extension; the heuristic is text-based on purpose so it covers nginx,
Apache, .htaccess, YAML manifests, and code in any language.

## Worked example

```bash
./verify.sh
```

Should print `PASS` with `bad findings: >=6` and `good findings: 0`.

## Suppression

Append `# cors-ok` or `// cors-ok` to one of the offending lines in the
window if the configuration is intentional and reviewed (e.g. a test
fixture that *expects* the misconfiguration).
