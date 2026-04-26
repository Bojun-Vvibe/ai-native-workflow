# `llm-output-orphan-fence-detector`

Pure-stdlib detector for **orphan Markdown code fences** in LLM output —
opening ` ``` ` (or `~~~`) with no matching closer, or a stray closer
with no opener. Both shapes are pernicious because every downstream
Markdown renderer reacts differently: some swallow the rest of the
document into a code block, others bleed `</code>` into prose, and
syntax highlighters often paint half the page wrong.

Three finding kinds:

- `unclosed_fence` — an opening fence with no matching closer before
  EOF. Reported on the opening line.
- `orphan_closing_fence` — a fence line at the top level (no opener
  on the stack) with empty info string AND no non-blank content
  after it. Heuristic, but reliable for the common "trailing stray
  closer" case.
- `mismatched_fence_char` — an opening ` ``` ` apparently closed by
  `~~~` (or vice versa). Per the CommonMark spec, the closer must
  use the same fence character as the opener; mixing them is a
  silent bug — the opener stays open and downstream content is
  swallowed.

Indentation up to 3 spaces is permitted on a fence (per CommonMark).
Anything indented 4+ spaces is an indented code block, not a fence,
and is ignored by this detector.

## When to use

- Pre-publish gate on any LLM-generated **runbook**, **PR
  description**, or **status update** that mixes prose and code.
  An unclosed fence near the bottom of a doc is the single most
  common reason a "the rest of the page is grey" bug ships.
- Inside a **review-loop** validator: the `(line_number, fence_char)`
  tuple is small and stable, so a stuck repair loop is detectable
  across attempts (same tuple twice → bail to a human).
- As a **streaming-output postcondition**: when you stream an LLM
  reply into a Markdown surface, run the detector at flush time —
  if `count > 0` the stream was truncated and you should re-issue
  the request rather than commit the partial reply.

## Usage

```
python3 detector.py [FILE ...]   # FILEs, or stdin if none
```

Exit code: `0` clean, `1` at least one finding. JSON on stdout.
Pure-stdlib; no third-party deps.

## Composition

- `agent-output-validation` — feed the JSON `findings` array into a
  repair prompt verbatim. Each finding's `raw_line` and
  `line_number` are enough context for the model to identify which
  fence to close.
- `llm-output-fenced-code-language-tag-missing-detector` —
  orthogonal: that template enforces *info string presence* on
  opening fences, this one enforces *that the fence is balanced*.
  Together they catch both "untagged code block" and "code block
  that never closes".
- `structured-output-repair-loop` — use `detect_orphan_fences` as
  the per-attempt validator. The `count` field collapses to a
  single integer per attempt for trivial loop-stuckness detection.

## Worked example

Input is `example_input.txt` — a doc with one clean fenced block
followed by a deliberately unclosed second fence (the model "ran
out of tokens" mid-block).

```
$ python3 detector.py example_input.txt
```

Verbatim output (exit 1):

```json
{
  "count": 1,
  "findings": [
    {
      "fence_char": "`",
      "fence_len": 3,
      "kind": "unclosed_fence",
      "line_number": 10,
      "raw_line": "```python"
    }
  ],
  "ok": false
}
```

Notes:

- The fence at line 3 (` ```python ` ... ` ``` ` at line 6) is
  correctly recognised as a complete, balanced block and is NOT
  flagged.
- The fence at line 10 (` ```python `) has no matching closer
  before EOF, so it's flagged as `unclosed_fence`. The
  `line_number` points at the opener, which is the actionable
  location for a repair prompt — telling the model "your fence at
  line 10 was never closed" is far more useful than pointing at
  EOF.
- `fence_char` and `fence_len` are reported separately so a
  repair prompt can quote the exact closer the model needs to
  emit (e.g. "close with three backticks on a line by
  themselves").

## Files

- `detector.py` — pure-stdlib detector + JSON renderer + CLI
- `example_input.txt` — planted-issue input (one good fence, one
  unclosed)
- `README.md` — this file

## Limitations

- The `orphan_closing_fence` heuristic only fires when the
  ambiguous fence has empty info string AND no non-blank content
  after it. A stray closer in the middle of a document is hard to
  distinguish from a deliberate empty-info opener whose body the
  model just hasn't produced yet — we conservatively report it as
  `unclosed_fence` instead.
- Fences inside HTML comments (`<!-- ``` -->`) are still tracked
  as fences. If your house style allows commented-out code blocks,
  strip HTML comments before running the detector.
- Indented code blocks (4+ leading spaces) are out of scope by
  design — they have no fence, so "orphan" doesn't apply.
- The detector does not validate the info string itself (e.g.
  `python` vs `pyhton`). That belongs to
  `llm-output-fenced-code-language-tag-missing-detector` and a
  language-allowlist linter.
