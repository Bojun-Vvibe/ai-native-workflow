# llm-output-elixir-process-sleep-in-genserver-callback-detector

Flags `Process.sleep/1`, `:timer.sleep/1`, and bare `sleep/1` calls
inside GenServer callback bodies in Elixir sources.

## The smell

```elixir
def handle_call(:fetch, _from, state) do
  Process.sleep(250)              # <-- freezes the GenServer mailbox
  {:reply, state.value, state}
end
```

A GenServer is a single-process serializer for its mailbox. Sleeping
inside a callback parks the *only* process that can drain it, so for
the full sleep duration:

- every queued `GenServer.call` blocks (and may hit its 5s default
  timeout),
- every queued `cast` and `info` waits its turn,
- the supervisor's `:shutdown` signal is ignored,
- pool-based wrappers (e.g., poolboy) start handing out other workers
  while this one sits idle.

A few hundred milliseconds of `Process.sleep/1` per request is enough
to convert a healthy GenServer into a queue bomb under modest load.

The right primitives are `Process.send_after/3`, `:timer.send_after/3`,
or `handle_continue` with state — all of which yield the process so
the mailbox keeps draining while the timer runs.

## Why LLMs produce it

`Process.sleep` is the most-cited "wait N milliseconds" snippet in
Elixir docs and tutorials. Asked to "rate-limit this handler" or "add
a small delay before responding", the model inlines the sleep without
recognising that the GenServer process model makes it a per-server
freeze, not a per-request delay. The "don't block a GenServer" rule
is process-architecture context rather than syntactic, so it is easy
to miss when generating a single function in isolation.

## How the detector works

Single-pass per-line scanner over `.ex` / `.exs` files:

1. **Mask comments and string literals.** `#` line comments,
   `"..."` / `'...'` strings, `\"\"\"...\"\"\"` and `'''...'''`
   heredocs, and Elixir sigils `~s|...|`, `~r/.../`, etc. (with the
   common delimiters `()[]{}<>|/"'`). Newlines preserved so line
   numbers stay accurate.
2. **Detect callback function heads** — `def handle_call(`,
   `def handle_cast(`, `def handle_info(`, `def handle_continue(`,
   `def init(`, `def terminate(`, `def code_change(`,
   `def format_status(` (and `defp` variants).
3. **Track scope stack.** A callback head marks the *next* `do`
   keyword as opening a "callback" scope. Plain `do` opens an "other"
   scope. `end` pops. One-liner `def head(...), do: <expr>` is
   recognised separately and its body is scanned inline.
4. **Flag** any `Process.sleep(`, `:timer.sleep(`, or bare `sleep(`
   whose enclosing scope stack contains a "callback" frame.

Stdlib only.

## False-positive caveats

- Helper functions defined *inside* a GenServer module but not on the
  callback list (e.g., a private `defp wait_for_ready do ... end`)
  are not callbacks themselves, but if they are *called from* a
  callback they will still block the same process. The detector does
  not chase calls — only the lexical body of the callback. To catch
  the indirect case, inline the helper or run a manual review.
- A multi-line `def head(...)` whose `do` lands on a later line is
  handled correctly, because `pending_callback` survives across lines
  until the next `do` token.
- A `do` token appearing inside a sigil that uses an unusual delimiter
  not in `()[]{}<>|/"'` may not be masked. The four heredoc forms and
  all common sigil delimiters are covered.
- Modules that `use GenStage` / `use Phoenix.Channel` / etc. share
  the same "single mailbox" hazard but use different callback names;
  this detector intentionally limits itself to the canonical
  `GenServer` callbacks. Extend `CALLBACK_NAMES` for those.

## Usage

```
python3 detector.py path/to/elixir/project
```

Exit code `0` if no hits, `1` if any.

## Worked example

Run against the bundled bad fixtures:

```
$ python3 detector.py templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/rate_limiter.ex:5: Process.sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/rate_limiter.ex:10: Process.sleep inside one-line GenServer callback handle_info at col 34: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/rate_limiter.ex:13: :timer.sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/worker.ex:5: Process.sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/worker.ex:10: Process.sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/worker.ex:15: :timer.sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
templates/llm-output-elixir-process-sleep-in-genserver-callback-detector/bad/worker.ex:20: sleep inside GenServer callback at col 5: blocks the GenServer mailbox; use Process.send_after or handle_continue
-- 7 hit(s)
```

Counts: `bad/` = 7 hits across 2 files (covers `init`, `handle_call`,
`handle_cast`, `handle_info`, `handle_continue`, `terminate`, plus a
one-liner `do:` form), `good/` = 0 hits across 2 files (one with
sleeps in non-callback helpers + correct `send_after` use, one
exercising the masker via a `@moduledoc` heredoc, a string literal,
and a `~s|...|` sigil that all mention `Process.sleep`).
