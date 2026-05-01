# llm-output-express-cors-reflect-origin-detector

Single-pass python3 stdlib scanner for Express / Node CORS code
that reflects the request `Origin` header as
`Access-Control-Allow-Origin` — usually paired with
`Access-Control-Allow-Credentials: true`. Catches both the `cors`
package shapes and hand-rolled middleware shapes that LLMs emit
constantly when "trying to make CORS work".

## Why it exists

Reflecting the request `Origin` is functionally equivalent to
`Access-Control-Allow-Origin: *`, except the spec actually allows
the browser to honour the response when credentials mode is on.
The result: any third-party site can make authenticated,
cookie-bearing requests to your API and read the response.

Three things make this a top LLM footgun:

1. The `cors` npm package's `origin: true` option *looks* like
   "enable CORS" but actually means "reflect every request
   Origin". Pair with `credentials: true` and you have universal
   credentialed CORS.
2. The "callback origin" form (`origin: function(o, cb){ cb(null,
   true) }`) is offered as a "more flexible" snippet but in its
   default LLM-emitted shape it never validates anything — it just
   echoes back true.
3. Hand-rolled middleware that copies `req.headers.origin` into
   the response header is a one-liner that "fixes" the dev-only
   "Access-Control-Allow-Origin not set" error, and it ships.

## What it flags

Node sources (`*.js`, `*.ts`, `*.mjs`, `*.cjs`, `*.jsx`, `*.tsx`):

- `cors({ origin: true })` →
  `cors-pkg-origin-true`.
- `cors({ origin: true, credentials: true })` (and any order) →
  `cors-pkg-origin-true-with-credentials` (high severity).
- `cors({ origin: function (o, cb) { cb(null, true) } })`,
  `cors({ origin: async function ... cb(null, true) ... })`, and
  `cors({ origin: (o) => true })` →
  `cors-pkg-origin-callback-always-true`.
- `res.setHeader('Access-Control-Allow-Origin', req.headers.origin)`
  (and `res.header(...)`, `res.set(...)`, `req.get('origin')`,
  `req.header('origin')`, `req.headers['origin']` variants) →
  `cors-manual-reflect-origin`.
- The same manual reflection in a file that also sets
  `Access-Control-Allow-Credentials: true` →
  `cors-manual-reflect-origin-with-credentials` (high severity).

## What it does NOT flag

- `cors({ origin: 'https://example.com' })` — explicit string
  allowlist.
- `cors({ origin: ['https://a.example', 'https://b.example'] })`
  — array allowlist.
- `cors({ origin: /^https:\/\/[a-z0-9-]+\.example\.com$/ })` —
  regex allowlist.
- `cors({ origin: false })` — disables CORS.
- Callback-form `cors` middleware that actually checks the
  `origin` argument against an allowlist before calling
  `cb(null, origin)` (only the "always true" shape is flagged).
- Lines marked with a trailing `// cors-reflect-ok` comment.
- Patterns inside `//` line comments.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 4 dangerous artefacts producing 5 findings;
`examples/good/` has 3 safe artefacts producing 0 findings.

```
$ ./verify.sh
bad findings:  5 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/arrow-reflector.ts:8:1: cors-pkg-origin-callback-always-true — cors({
examples/bad/arrow-reflector.ts:15:1: cors-manual-reflect-origin — res.set("Access-Control-Allow-Origin", req.headers.origin);
examples/bad/callback-reflector.ts:8:1: cors-pkg-origin-callback-always-true — cors({
examples/bad/credentialed.js:10:1: cors-pkg-origin-true-with-credentials — cors({
examples/bad/manual-middleware.js:8:1: cors-manual-reflect-origin-with-credentials — res.setHeader("Access-Control-Allow-Origin", req.headers.origin);
# 5 finding(s)
```

(The arrow-reflector file gets only one `cors-*` finding because
the manual `res.set(..., req.headers.origin)` line in the same
file does not also set Allow-Credentials, so it is reported as
the lower-severity `cors-manual-reflect-origin` rather than the
upgraded form.)

## Suppression

Add `// cors-reflect-ok` at the end of any line you have audited.
Typical example: a deliberate same-origin-only debug endpoint
inside a feature-flagged dev block.

## Layout

```
llm-output-express-cors-reflect-origin-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── arrow-reflector.ts
    │   ├── callback-reflector.ts
    │   ├── credentialed.js
    │   └── manual-middleware.js
    └── good/
        ├── allowlist.js
        ├── callback-allowlist.ts
        └── regex-and-fixed.js
```

## Limitations

- The scanner does line / regex matching. It will not catch
  `origin` values built dynamically (e.g. constructed from
  `process.env`), and it cannot prove a callback-form reflector
  is actually safe — it only flags the "always true" shape.
- The "with-credentials" upgrade for manual reflection is
  file-scoped: any `Access-Control-Allow-Credentials: true`
  anywhere in the same file will upgrade *every* manual
  reflection finding in that file. This favours over-reporting
  severity over under-reporting.
- Only the `cors` npm package's options shape is recognised; the
  Koa `@koa/cors`, Fastify `@fastify/cors`, NestJS `enableCors`,
  and Hapi shapes are not yet covered. The manual-reflection
  detection works regardless of framework, since it keys on the
  `Access-Control-Allow-Origin` response header.
- TypeScript object literals with computed property names
  (`[KEY]: true`) are not parsed; only literal `origin:` and
  `credentials:` keys are recognised.
