# llm-output-go-error-ignored-detector

A small Python 3 stdlib sniffer for Go source where an `error` return value
is silently dropped via assignment to the blank identifier `_`.

## Why it matters for LLM-generated output

When LLMs hand back Go snippets they often shorten error handling to keep
the example "tidy" — typical patterns include:

```go
data, _ := json.Marshal(payload)   // error discarded
_ = resp.Body.Close()              // error discarded
_, _ = http.Get(url)               // both values discarded
```

Each of those is a real production foot-gun: `Marshal` fails on cyclic
structs, `Close` reports flush errors on buffered writers, and `Get` fails
on DNS / TLS / network errors. Code reviewers reject these patterns; this
detector catches them before they ship.

## Rule

Flag a line when **all** of the following hold:

1. The line is an assignment (`=` or `:=`) whose left-hand side contains
   the blank identifier `_` in any tuple position.
2. The right-hand side is a function/method call.
3. If the LHS is the single token `_` (i.e. `_ = call(...)`), the call
   name must match a heuristic list of fallible Go stdlib idioms
   (`Open`, `Close`, `Read`, `Write`, `Marshal`, `Unmarshal`, `Get`,
   `Post`, `Do`, `Exec`, `Query`, …) to avoid flagging side-effect-only
   calls that legitimately return `(T,)` with no error.

Multi-return cases (`x, _ := f()`, `_, _ = f()`) are always flagged: in
idiomatic Go a function returning two values where the second is dropped
is overwhelmingly an `(T, error)` pair.

## Limitations

- Heuristic, not a type checker. For exact analysis use `errcheck` or
  `staticcheck SA9003`. This template is meant to be embedded in fast
  pre-commit / LLM-output review hooks where pulling a Go toolchain is
  too heavy.
- Comments inside string literals could in theory confuse the regex; the
  line-based stripper handles `//` and `/* */` comments but not
  pathologically embedded `:=` inside strings.

## Usage

```
python3 detector.py <file.go> [<file.go> ...]
```

Prints `path:line: ignored error: <text>` for each violation, then a
trailing `findings: N` line. Exit code equals the finding count
(capped at 255).

## Worked example

```
$ python3 detector.py examples/bad.go
examples/bad.go:11: ignored error: f, _ := os.Open("/tmp/x")
examples/bad.go:12: ignored error: _ = f.Close()
examples/bad.go:15: ignored error: data, _ := json.Marshal(map[string]int{"a": 1})
examples/bad.go:19: ignored error: _, _ = http.Get("https://example.com")
examples/bad.go:22: ignored error: resp, _ := http.Get("https://example.com/x")
examples/bad.go:23: ignored error: _ = resp.Body.Close()
findings: 6

$ python3 detector.py examples/good.go
findings: 0
```

## Files

- `detector.py` — the sniffer.
- `examples/bad.go` — 4 distinct violation patterns (6 flagged lines).
- `examples/good.go` — same logic with proper `if err != nil` handling.
