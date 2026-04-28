# llm-output-go-mutex-by-value-detector

Detects Go code (in fenced markdown blocks or raw `.go` files) that
copies a `sync.Mutex` / `sync.RWMutex` / `sync.WaitGroup` / `sync.Once`
/ `sync.Cond` / `sync.Map` value. Copying these types silently breaks
mutual exclusion: the goroutine ends up locking a different mutex than
the one whoever else thinks they're locking. `go vet` catches the
classic cases; LLM-generated tutorial-style Go is the most common
source of this smell because the model writes value receivers for
"simplicity" without thinking about the embedded lock.

## Heuristic

Three checks, applied to each Go fence (or to the whole file if no
fences are detected):

1. **Field declared by value in a struct.** `mu sync.Mutex` in a
   `type X struct { ... }` block. Pointer fields (`mu *sync.Mutex`)
   are intentionally allowed.
2. **Anonymous embed by value.** `sync.Mutex` on its own line inside
   a struct.
3. **Function/method parameter by value.** Any `name sync.Mutex`
   inside a parameter list, no leading `*`.
4. **Value receiver on a struct that contains a sync mutex field.**
   `func (s Foo) Bar()` where `Foo` was previously seen with an
   embedded mutex. Even if the field itself is a pointer, this is
   still copying any other lock state in `Foo`, but we restrict the
   check to value-mutex structs to keep false positives low.

Comments and string/raw-string literals are scrubbed before matching.

## Usage

```
python3 detector.py path/to/file.md
python3 detector.py path/to/file.go
```

Findings print as `path:line:col: msg` and the script ends with
`total findings: N`.

## False-positive notes

- `sync.Locker` interface values are not flagged (in practice the
  underlying value is a pointer).
- The `*sync.Mutex` pointer pattern is correctly considered safe.
- Field name `mu sync.Mutex` is technically fine *if* the enclosing
  struct is only ever taken by pointer. The detector still flags it
  because LLM output frequently combines such a field with a
  value-receiver method later — this is the highest-signal pattern
  to catch in generated tutorial code, and `go vet` will agree.
- We do not parse generics or fully expand type aliases. `type M = sync.Mutex` will not be tracked through the alias.

## Worked example

`examples/bad.md` contains four distinct copies of a sync mutex (field-by-value,
anonymous embed, value parameter, and value receiver). The detector
fires four findings. `examples/good.md` uses pointer receivers and
pointer fields throughout and fires zero.
