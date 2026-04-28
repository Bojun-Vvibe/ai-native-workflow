# llm-output-go-defer-in-loop-detector

Flags `defer` statements that appear inside `for` loops in Go source.

## The smell

```go
for _, p := range paths {
    f, err := os.Open(p)
    if err != nil { return err }
    defer f.Close()   // <-- fires at function return, NOT loop iteration
    _ = f
}
```

`defer` runs when the **enclosing function** returns, not when the
enclosing block exits. Putting `defer f.Close()` inside a loop that
opens a file per iteration accumulates open file descriptors for the
lifetime of the entire function — a classic leak that crashes long-running
servers under FD exhaustion.

## Why LLMs produce it

The "open / defer close" idiom is the most repeated Go snippet in
training data. When the model generalizes from "open a file" to "open
many files", it carries the `defer` along without adjusting scope. The
fix — wrapping the body in a closure or using an explicit `Close()` at
the end of the iteration — is rarer in training data, so the model
defaults to the wrong shape.

## How the detector works

Single-pass scanner over `.go` files:

1. **Mask comments and string/rune literals.** Block comments
   (`/* ... */`), line comments (`// ...`), interpreted strings
   (`"..."`), raw strings (`` `...` ``), and runes (`'.'`) are all
   replaced with spaces so keywords inside them don't trigger.
2. **Track scope stack.** Each `func` and `for` keyword is queued as a
   "pending scope kind" and applied to the next `{`. Plain `{` pushes
   `block`. `}` pops.
3. **Flag `defer` whose enclosing scope chain (from the most recent
   `func` downward) contains a `for`.**

Stdlib only.

## False-positive caveats

- Method values named `defer` or `for` are not legal Go identifiers, so
  the keyword-as-identifier collision case doesn't arise.
- Multi-line `for` headers (`for i := 0; \n i < 10; \n i++ {`) work
  because the `{` is what opens the scope.
- `select { case <-ch: ... }` does not push a `for` scope, so a
  `defer` inside a `select` arm of a `for { select { ... } }` loop
  *will* still fire (correctly — the `for` is on the stack).
- Generated code (`*_gen.go`, `*_pb.go`) is scanned the same as
  hand-written code; filter externally if undesired.
- An anonymous closure `func() { defer ... }()` inside a `for` will
  flag — but that pattern is the **fix**, so the detector emits a
  false positive there. If you adopt the closure pattern widely,
  add a `// nolint: defer-in-loop` style suppression upstream of the
  scanner.

## Usage

```
python3 detector.py path/to/go/project
```

Exit code `0` if no hits, `1` if any.

## Smoke test

See `SMOKE.md`.
