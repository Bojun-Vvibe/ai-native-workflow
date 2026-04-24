# `model-output-truncation-detector`

A heuristic detector for "the model hit `max_tokens` mid-thought,"
plus a continuation-prompt builder for asking the model to resume
without restating. Fuses the upstream `finish_reason` signal (when
available) with structural anomalies in the text itself.

## The problem

LLM APIs return a `finish_reason` field that *can* tell you the
generation was cut off (`finish_reason="length"`). In practice you
cannot rely on it alone for two reasons:

  1. Many wrappers, frameworks, and proxy layers strip metadata and
     hand you back a string. By the time the truncated text reaches
     the code that needs to decide "should I ask for more?" the
     finish_reason is gone.
  2. `finish_reason="length"` tells you the limit was hit; it does
     not tell you the response was incomplete. A response that
     happened to fit exactly into the budget is technically
     `length`-truncated but semantically fine. Conversely, a model
     that wandered into a thought it couldn't compress and then
     stopped mid-word with `finish_reason="stop"` (rare but real,
     usually due to a stop-sequence collision) looks "clean" by the
     metadata alone.

So you need both: the metadata signal *and* a structural read of
the text. This template gives you the structural read in one
function call, combines it with the metadata signal, and emits a
verdict on a four-level scale that downstream code can branch on.

## The bug class it prevents

Silent partial output. The downstream symptoms vary by domain:

  - A code-generation pipeline ships a Python file ending mid-`def`,
    which the linter rejects but the agent loop interprets as "the
    edit failed" and rolls back instead of asking for completion.
  - A summarizer emits a final bullet list whose last bullet trails
    off mid-noun-phrase ("then we should "), which a reviewer reads
    as "the author forgot the rest" rather than "the model ran out
    of tokens."
  - A tool-call producer emits an opening `{` with no `}`, which the
    JSON parser rejects with a useless message and the model is
    asked to "fix the JSON" rather than "continue from here."

In all three cases the right move is the same — ask the model to
continue from exactly where it stopped, without restating — and
this template makes that the easy path.

## Approach

`detect(text, finish_reason=None)` returns a `TruncationVerdict`
with four possible levels:

| Level | Meaning | Typical caller action |
|---|---|---|
| `TRUNCATED` | `finish_reason="length"`, OR strong + corroborating structural signals | Send a continuation request |
| `LIKELY_TRUNCATED` | Strong structural signal (e.g. unclosed code fence) without explicit "stop" | Send a continuation request |
| `SUSPICIOUS` | One weak structural signal, no metadata | Log and ship; flag for review |
| `CLEAN` | `finish_reason="stop"` and no anomalies, or no signals and no metadata | Ship as-is |

Structural signals computed:

  - **`unclosed_code_fence`** — odd number of triple-backtick fences.
  - **`unclosed_brackets=N`** — character-level bracket balance for
    `()`, `[]`, `{}`, with naive string-literal awareness so a `}`
    inside `"foo}"` doesn't fool the counter.
  - **`ends_mid_word`** — last non-whitespace char is a letter and
    no sentence terminator appears in the trailing 40 chars.
  - **`ends_mid_bullet`** — last line is a very short bullet item,
    or last line ends mid-word and the previous line was a bullet.

When `finish_reason="stop"` is present, structural signals are
deliberately **downgraded** to `SUSPICIOUS` rather than escalated
to `TRUNCATED`. Models legitimately produce odd-looking endings —
a code block that ends a file, a bullet list that ends a section —
and a confident "stop" from upstream is the strongest available
evidence the response is intentionally complete. The opposite
asymmetry (`finish_reason="length"`) is treated as authoritative:
if the upstream says the limit was hit, that's truncation, full
stop, regardless of how clean the tail looks.

## The continuation prompt

`build_continuation_prompt(verdict, original_request, partial)`
returns a string ready to send back to the model. It bundles three
critical pieces:

  1. The detected signals, so the model gets some self-introspection
     fuel ("I was cut off because I hit length, and the tail
     suggests I was mid-word").
  2. The original request verbatim, so the model can re-anchor
     without the caller having to also re-pass the system prompt.
  3. The exact last 200 characters produced, with an explicit
     instruction to resume from that point and **NOT restate**.

The "do not restate" instruction is the half of this that matters
most in practice. The most common failure mode of naive
continuation is the model echoing its last paragraph back to set
context, which both wastes budget and produces a stitch seam the
caller has to detect and remove. The prompt template here has been
tuned to minimize that.

## Contract

| Property | Guarantee |
|---|---|
| Determinism | `detect(text, fr)` is pure: same inputs produce the same verdict every time. |
| Stdlib-only | No third-party deps. Works anywhere Python 3.9+ runs. |
| Fast | O(len(text)) with small constants. Safe to call on every model response in a hot loop. |
| Conservative | When in doubt, prefers `SUSPICIOUS` over `LIKELY_TRUNCATED`, and `LIKELY_TRUNCATED` over `TRUNCATED`. False-positive continuations are expensive (extra round-trip + token cost). |
| Trusts explicit "stop" | Structural anomalies are downgraded when upstream confidently says generation completed naturally. |

## When to use this

- Any agent loop that processes streaming or chunked LLM output.
- Tool-output validators that need to decide "retry vs. continue."
- Eval harnesses that need to mark "incomplete" runs distinctly
  from "wrong" ones.
- Pipelines whose model calls go through a wrapper that strips
  `finish_reason` (which is most of them).

## When NOT to use this

- When you have full structured-output grounding (JSON schema,
  function calls). Use the schema validator's "incomplete" signal
  instead — it's exact, this is heuristic.
- When you do not control the continuation. The detector without
  the continuation builder is half a tool; if your runtime can't
  send a follow-up, log the verdict and move on.
- For non-text outputs. The signals here assume natural language
  or code. Audio/image truncation is a different problem.

## Integration notes

- The detector takes the *full* response text. If you stream, accumulate first.
- `build_continuation_prompt` raises `ValueError` if you call it on
  a `CLEAN` verdict. That's intentional: continuing a clean
  response is usually a bug.
- Pair with `prompt-token-budget-guard` (when shipped) so that a
  detected truncation doesn't cause a continuation that *also*
  truncates because the new prompt is too large.
- Pair with `agent-decision-log-format` so the verdict is logged
  alongside the decision to continue/ship — this lets you
  back-test the heuristic against real production outcomes.

## Worked example output

Running `python3 examples/run.py` (stdlib only, no setup):

```
case                                verdict            signals
------------------------------------------------------------------------------------------
clean_with_stop                     CLEAN              -
length_signal_only                  TRUNCATED          ends_mid_word
unclosed_code_fence_no_signal       LIKELY_TRUNCATED   unclosed_code_fence
mid_bullet_no_signal                LIKELY_TRUNCATED   ends_mid_word,ends_mid_bullet
stop_with_innocent_code_block       CLEAN              -
ends_mid_word_no_signal             SUSPICIOUS         ends_mid_word

=== continuation prompt for first TRUNCATED case ===
Your previous response was cut off mid-output.
Detected signals: ends_mid_word
finish_reason was: 'length'

Original request:
---
Walk me through how to load and validate config.
---

The exact last characters you produced were:
---
Step one is to initialize the buffer. Step two is to populate it with
---

Resume from exactly that point. Do NOT restate, summarize, or apologize. Output only the continuation, starting with the very next character that should follow the tail above. If you were inside a code block, stay inside it; if a sentence was mid-word, finish the word.

ALL CHECKS PASSED
```

The cases exercise: clean stop, explicit length signal, structural
anomaly with no metadata, multi-signal mid-bullet stop, the
asymmetric "stop trusts away an innocent code block," and a
single-weak-signal SUSPICIOUS case.
