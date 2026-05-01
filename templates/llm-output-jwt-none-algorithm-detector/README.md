# llm-output-jwt-none-algorithm-detector

Single-pass python3 stdlib scanner for JWT verification code paths
that accept the `none` algorithm or otherwise skip signature
verification. Flags the canonical "permissive verifier" shapes
LLMs emit across Python (`PyJWT`), Node (`jsonwebtoken`), and Go
(`golang-jwt`).

## Why it exists

The JWT spec allows an `alg: none` token whose signature is the
empty string. A verifier that does not pin an explicit algorithm
list — or worse, allows `"none"` in that list, or short-circuits
verification when the header says `none` — will accept any forged
token as authentic. This is one of the oldest, best-documented
JWT footguns, and it is alive and well in code suggestions today
because:

- Many JWT libraries default to "accept whatever alg the header
  claims" if the caller does not pin one.
- `jwt.decode()` (parse-only) and `jwt.verify()` look almost
  identical, and snippet templates frequently reach for `decode`
  because it is shorter.
- Go `golang-jwt` keyfuncs that switch on `t.Method` still have to
  *not* handle `*jwt.SigningMethodNone`, which LLMs sometimes add
  for "completeness".

## What it flags

Python (`*.py`):

- `jwt.decode(...)` with no `algorithms=` kwarg →
  `jwt-py-decode-missing-algorithms`.
- `jwt.decode(..., algorithms=None)` →
  `jwt-py-decode-algorithms-none`.
- `jwt.decode(..., algorithms=[])` →
  `jwt-py-decode-algorithms-empty`.
- `jwt.decode(..., algorithms=[..., "none", ...])` →
  `jwt-py-decode-algorithms-includes-none`.
- `jwt.decode(..., verify=False)` →
  `jwt-py-decode-verify-false`.
- `jwt.decode(..., options={"verify_signature": False})` →
  `jwt-py-decode-verify-signature-false`.

Node (`*.js`, `*.ts`, `*.mjs`, `*.cjs`, `*.jsx`, `*.tsx`):

- `jwt.verify(...)` / `jsonwebtoken.verify(...)` with no
  `algorithms:` option → `jwt-js-verify-missing-algorithms`.
- Same call with `algorithms: []` →
  `jwt-js-verify-algorithms-empty`.
- Same call with `algorithms: [..., "none", ...]` →
  `jwt-js-verify-algorithms-includes-none`.
- `jwt.decode(...)` whose result is bound to an identifier whose
  name implies the caller treats it as authenticated (`verified`,
  `authenticated`, `trusted`, `authPayload`, `isValid`) →
  `jwt-js-decode-used-as-verify`.

Go (`*.go`):

- Any reference to `jwt.SigningMethodNone` / `SigningMethodNone`
  → `jwt-go-signing-method-none`.

Any source file (cross-language):

- Branch of the form `alg == "none"` (also `===`, `=`, `:`,
  `.equals(...)`, `.toLowerCase() == ...`) →
  `jwt-alg-none-branch`.

## What it does NOT flag

- `jwt.decode(token, key, algorithms=["HS256"])` etc. — pinned,
  signature checked, no `none`.
- `jwt.verify(token, key, { algorithms: ["RS256"] }, ...)` —
  pinned in Node.
- `jwt.decode(token, { complete: true })` in Node when its result
  is *not* used as authentication (no `verified` / `authenticated`
  / `trusted` identifier nearby on the same line).
- Lines marked with a trailing `# jwt-none-ok` or `// jwt-none-ok`
  comment.
- Patterns inside `#` or `//` comment lines.

## Usage

```bash
python3 detect.py path/to/file_or_dir [more paths ...]
```

Exit code:

- `0` — no findings
- `1` — at least one finding
- `2` — usage error

## Worked example

`examples/bad/` has 4 dangerous artefacts producing 7 findings;
`examples/good/` has 3 safe artefacts producing 0 findings.

```
$ ./verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

Verbatim scanner output on `examples/bad/`:

```
examples/bad/auth.py:5:1: jwt-py-decode-missing-algorithms — payload = jwt.decode(token, secret)
examples/bad/auth.py:10:1: jwt-py-decode-missing-algorithms — return jwt.decode(token, options={"verify_signature": False})
examples/bad/auth.py:10:1: jwt-py-decode-verify-signature-false — return jwt.decode(token, options={"verify_signature": False})
examples/bad/middleware.js:7:1: jwt-js-verify-missing-algorithms — jwt.verify(token, process.env.JWT_SECRET, function (err, decoded) {
examples/bad/middleware.js:16:1: jwt-js-decode-used-as-verify — const verified = jwt.decode(token);
examples/bad/verify.go:15:1: jwt-go-signing-method-none — if _, ok := t.Method.(*jwt.SigningMethodNone); ok {
examples/bad/verify.go:27:1: jwt-alg-none-branch — if alg == "none" {
# 7 finding(s)
```

## Suppression

Add `# jwt-none-ok` (Python / Ruby / shell) or `// jwt-none-ok`
(JS / TS / Go / Java) at the end of any line you have audited —
for example, a deliberate test fixture that round-trips an
unsigned JWT to assert the verifier rejects it.

## Layout

```
llm-output-jwt-none-algorithm-detector/
├── README.md
├── detect.py
├── verify.sh
└── examples/
    ├── bad/
    │   ├── auth.py
    │   ├── middleware.js
    │   ├── permissive.py
    │   └── verify.go
    └── good/
        ├── auth.py
        ├── middleware.js
        └── verify.go
```

## Limitations

- The Python call-span scanner uses a naive paren counter that
  respects single/double/backtick string literals but does not
  understand triple-quoted strings or f-string expressions — a
  `jwt.decode(` literal embedded in a triple-quoted string will
  be parsed as a real call.
- The "include `none`" detection is a substring match for the
  literal token `"none"` / `'none'` inside the `algorithms=` list
  body. A dynamically-built list (e.g. variable interpolation)
  will not be inspected; pin the list literally.
- Go coverage flags `SigningMethodNone` references but does not
  attempt to prove that the keyfunc actually returns a key for
  that method — any mention is treated as suspicious because the
  symbol has effectively one use.
- Cross-language `alg == "none"` heuristic only catches the most
  literal branch shapes; obfuscated comparisons (e.g. comparing
  byte arrays) will be missed.
- This scanner does not cover Java (`io.jsonwebtoken`/`nimbus`),
  Ruby (`ruby-jwt`), or .NET — patterns are similar and could be
  added with the same call-span helper.
