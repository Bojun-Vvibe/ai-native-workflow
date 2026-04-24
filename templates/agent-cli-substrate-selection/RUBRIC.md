# RUBRIC — five-clause decision rule

Run these five clauses against the task in order. The first one that fires picks the substrate class. Stop reading after the first hit — later clauses can rationalize but cannot override.

## Clause 1 — File discovery requirement

**Question.** Does the task require the CLI to read or write files that the human has not already piped into stdin or named on the command line?

- **Yes** → agent CLI. A pre-agency CLI cannot discover, list, or open files; emulating this with shell wrappers re-implements the agent loop badly.
- **No** → continue to Clause 2.

Diagnostic: if your draft invocation contains `find`, `fd`, `ls`, or a glob that you'd then have to feed back into prompts, you're emulating Clause 1.

## Clause 2 — Iterative refinement against ground truth

**Question.** Does the task require running something (tests, build, linter, target binary), reading the result, and feeding it back into the model for another attempt?

- **Yes** → agent CLI. The loop *is* the value. Pre-agency CLIs force the human to be the loop, which makes every iteration a context-switch tax.
- **No** → continue to Clause 3.

Diagnostic: if a one-shot answer that is wrong leaves you no feedback channel except "ask again with more context," you're inside Clause 2.

## Clause 3 — One transform on a known input

**Question.** Is the task a single transformation on a single input that's already in your hand, with the output flowing to a downstream pipe stage (file, another command, clipboard)?

- **Yes** → pre-agency LLM CLI. Agent CLIs add latency, log noise, and cost without adding capability for one-shot transforms.
- **No** → continue to Clause 4.

Diagnostic: if your draft invocation looks like `<command-that-produces-input> | <ai-cli> | <command-that-consumes-output>`, you're inside Clause 3.

## Clause 4 — Batch shape

**Question.** Is the task the same transform applied independently across N inputs, with results collected into one place?

- **Yes** → pre-agency LLM CLI in a `for` loop, `xargs`, or `parallel`. An agent CLI per input compounds harness overhead N times and breaks prompt-cache reuse.
- **No** → continue to Clause 5.

Diagnostic: if you'd describe the task as "do X for each Y," and the per-Y work doesn't depend on other Ys, you're inside Clause 4.

## Clause 5 — Default

If Clauses 1–4 are all ambiguous, default to **pre-agency**. Two asymmetric reasons:

1. It is cheaper to upgrade a pipe to a mission later than to downgrade a mission to a pipe. Mission YAML, agent profiles, tool registries, and harness configs are sticky.
2. Pre-agency mistakes surface immediately as "the answer was wrong." Agent mistakes can take 40 turns to reveal themselves and cost 30× more by the time you notice.

## Tiebreakers when two clauses both seem to fire

- Clauses 1 and 3 both fire (one transform but the input is "the contents of file X"): treat as **Clause 3**, pre-agency. The human, not the CLI, opens file X via `cat` or `<`. The CLI just transforms what's piped in.
- Clauses 2 and 4 both fire (refining a transform across N inputs, e.g. translating 50 docs and re-running quality checks): split the task. Run **Clause 4** (batch pre-agency) for the bulk transform, then **Clause 2** (agent) for the fraction that fail quality checks.
- Clauses 1 and 4 both fire (batch task that needs to discover its own inputs, e.g. "summarize every README in this monorepo"): the discovery is the human's job. Run `fd README.md` or `find . -name README.md`, pipe the list into a `for` loop, and treat each iteration as **Clause 3** pre-agency.

## What this rubric does not decide

- **Which model** to use inside the chosen class. That's a separate axis (cost, context window, eval quality, locality).
- **Which specific CLI** within the chosen class. The classifier prompt picks among your installed inventory; preference order is (a) lowest harness overhead at task scale, (b) cleanest log shape for what you're going to do next with it.
- **Whether to use AI at all.** This rubric assumes you've already decided yes. If a `sed` one-liner does it, use `sed`.
