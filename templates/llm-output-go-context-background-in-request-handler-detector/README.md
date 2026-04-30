# llm-output-go-context-background-in-request-handler-detector

A pure-stdlib python3 line scanner that flags Go code which calls
`context.Background()` or `context.TODO()` from inside a function
that **already has a request-scoped `context.Context` available** —
typically an HTTP handler (`*http.Request`), a gRPC handler, or any
function whose signature accepts a `context.Context`.

When a handler ignores its inbound context and constructs a fresh
`context.Background()` for the downstream DB / RPC / HTTP call, it
silently discards:

* the request deadline (the call lives forever even after the client
  closed the connection),
* the cancellation signal (the goroutine never wakes up),
* trace/correlation IDs propagated through the context,
* any auth metadata attached to the context.

The classic symptom is a request the client gave up on five seconds
ago, but the server keeps a connection pinned to the DB for another
minute because the inner query was issued with `context.Background()`.

LLMs reach for `context.Background()` because:

1. They saw it in a snippet that initialised a long-lived background
   worker and pattern-matched without realising the new call site is
   request-scoped.
2. They wanted to "decouple" the inner call from a flaky upstream.
3. They could not name the parameter (`ctx` vs `r.Context()`) and
   `context.Background()` always compiles.

## What this flags

In `*.go` files: `context.Background()` or `context.TODO()` invoked
inside a function whose enclosing scope has either:

* a parameter typed `context.Context` (any name), or
* a parameter named `r` / `req` / `request` typed `*http.Request`.

Both top-level functions, methods, and `func(...) { ... }` closures
are tracked. Nested function literals get their own scope.

## What this does NOT flag

* `context.Background()` in `main()`, `init()`, or any function
  whose parameters do not include a `context.Context` or
  `*http.Request`.
* Calls inside `/* ... */` block comments.
* Lines suffixed with the suppression marker `// ctx-background-ok`
  (used for legitimate "detached" goroutines that must outlive the
  request — e.g. async writes to a metric pipeline).

## Failure-mode references

* Go context propagation guidance:
  https://pkg.go.dev/context#pkg-overview ("Do not store Contexts
  inside a struct type; instead, pass a Context explicitly to each
  function that needs it.")
* `staticcheck` SA1029 (storing context in struct) is related but
  catches a different shape; this detector targets the inverse
  mistake: ignoring the inbound context entirely.

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Scans `*.go` under any directory passed in. Exit `1` if any
findings, `0` otherwise. python3 stdlib only — no Go toolchain
required.

## Verified worked example

```
$ bash test.sh
bad findings: 6 (expected 6)
good findings: 0 (expected 0)
PASS
```

Real run output over the fixtures:

```
$ python3 detector.py fixtures/bad/
fixtures/bad/02_ctx_param.go:7: context.Background/TODO inside request-scoped handler: bg := context.Background()
fixtures/bad/02_ctx_param.go:9: context.Background/TODO inside request-scoped handler: return downstream.Call(context.TODO(), id)
fixtures/bad/04_closure.go:11: context.Background/TODO inside request-scoped handler: _ = client.Do(context.Background(), r.URL.Path)
fixtures/bad/03_grpc_handler.go:8: context.Background/TODO inside request-scoped handler: res, err := cache.Get(context.Background(), req.Key)
fixtures/bad/01_http_handler.go:9: context.Background/TODO inside request-scoped handler: ctx := context.Background()
fixtures/bad/01_http_handler.go:11: context.Background/TODO inside request-scoped handler: row := db.QueryRowContext(context.Background(), "SELECT 1")

$ python3 detector.py fixtures/good/
(no output, exit 0)
```

## Limitations

* Single-line scanner with brace-depth tracking. Complex multi-line
  function signatures whose closing `)` and opening `{` are split
  across many lines may confuse the scope tracker.
* Generic functions whose context parameter is typed via an
  interface alias (e.g. `Ctx` re-export) are not recognised.
* The detector does not look inside type definitions; calling
  `context.Background()` in a `var ctx = ...` package-level
  declaration is correctly NOT flagged.

## Suppression

After review, append the suppression marker to the line:

```go
go writer.Flush(context.Background()) // ctx-background-ok
```
