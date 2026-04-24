# agent-cli-substrate-selection

A decision template for picking the right AI CLI substrate for a given task — before you start. Operationalizes the **pre-agency-LLM-CLI vs agent-CLI** taxonomy as a concrete, prompt-driven decision rule so you stop reaching for a 10-tool agent loop when a `cat | llm` pipe would have shipped the answer in 30 seconds, and stop trying to glue 47 shell scripts around `llm` when you actually need an agent loop with tool use.

## When to use this

- You have ≥ 2 AI CLIs installed (e.g. some mix of `llm`, `aichat`, `codex`, `claude`, `opencode`, `crush`, `aider`, `gemini`, `forge`, `qwen-code`, `continue`, `plandex`).
- You catch yourself reaching for the same CLI by reflex regardless of task shape.
- You suspect substrate mismatch is bleeding cost, latency, or quality (signs: agent loop on a one-shot transform, scripted-pipe contortion around something that wants tool use, "I asked it to read 8 files" against a stateless completion CLI).
- You're onboarding a new task class and want to write down which substrate it should land on, *once*, before reflex sets it for you.

## When NOT to use this

- Single-substrate environment (only `claude` installed; the decision is degenerate).
- The task is interactive exploration where the human is the loop — substrate choice is dominated by personal habit and that's fine.
- You're benchmarking substrates against each other; this template assumes the goal is to *use* a substrate, not measure it.

## The taxonomy this rests on

Two classes, separated by **whether the CLI initiates further actions on its own after the first model reply**:

- **pre-agency LLM CLI** — sends prompt → returns text → exits. No tool calls, no follow-up turns, no filesystem mutation, no shell execution. Examples: `llm`, `aichat` (chat-mode aside), `gemini -p`, anything you can replace with `curl https://api.openai.com/v1/chat/completions`. Composes via shell pipes; logs are flat; cost is one round trip.
- **agent CLI** — runs a loop: model reply may include tool calls (read file, edit file, run shell, search web), CLI executes them, feeds results back to the model, repeats until stop condition. Examples: `claude`, `codex`, `opencode`, `crush`, `aider`, `forge`, `qwen-code`, `continue`, `plandex`. Composes via missions; logs are nested; cost is N round trips with growing context.

This is a **taxonomic** split, not a gradient. A pre-agency CLI does not become an agent CLI by adding `--system "use the file tool"`; it lacks the loop. An agent CLI does not become pre-agency by passing `--max-turns 1`; it still ships the agent runtime, the tool registry, and the harness overhead.

The choice between them is rarely about model quality (both classes can call GPT-5 or Sonnet 4.5). It's about **task shape**.

## The five-clause decision rule

Run these in order. The first clause that fires picks the class.

1. **Does the task require reading/writing files the human hasn't already piped in?** → agent CLI. Pre-agency CLIs cannot discover files; you'd be writing a wrapper that re-implements an agent loop.
2. **Does the task require iterative refinement against ground truth (run tests, parse stack trace, fix, re-run)?** → agent CLI. The loop is the value; pre-agency CLIs force the human to be the loop.
3. **Is the task one transform on a known input, with the output going to a downstream pipe stage?** → pre-agency LLM CLI. Agent CLIs add latency, log noise, and cost without adding capability here.
4. **Is the task batch-shaped (run the same transform across N inputs, collect outputs)?** → pre-agency LLM CLI in a `for` loop or `xargs`. An agent CLI per input compounds harness overhead N times.
5. **Default if all four are ambiguous** → pre-agency. It's cheaper to upgrade a pipe to a mission than to downgrade a mission to a pipe; agent CLIs are sticky once you've written the mission YAML.

## Substrate match matrix

The matrix below lists common task classes and the substrate class they should land on. Adapt the right column to your installed CLI inventory.

| Task class | Class | Why |
|---|---|---|
| Summarize one PR diff | pre-agency | one transform, known input |
| Triage 50 PRs into a queue | pre-agency in a loop | batch transform |
| Refactor a TS module to use Result types | agent | reads multiple files, runs `tsc`, iterates |
| Write a one-paragraph commit message | pre-agency | one transform on the staged diff |
| Investigate why 3 tests are failing | agent | needs to read tests, run, parse, hypothesize |
| Translate a config file format | pre-agency | one transform, known input |
| Extract entities from 200 emails | pre-agency in a loop | batch transform |
| Add a new CLI subcommand with tests | agent | reads existing patterns, edits, runs tests |
| Generate a markdown table from JSON | pre-agency | one transform, known input |
| RAG over local notes | depends — pre-agency for one-shot Q&A (`llm` + embeddings plugin); agent for "find inconsistencies across notes" |
| Daily OSS digest of N repos | pre-agency in a loop, joined by an agent at the end |
| Reverse-engineer an undocumented binary | agent | reads, runs, observes, hypothesizes, iterates |

## Five mismatched-deployment failure modes

When the rule above is violated, the failure looks like one of these. Knowing the symptom lets you spot mismatch in someone else's setup (and your own) without re-running the decision.

1. **Agent-on-pipe.** Agent CLI invoked for a single transform on stdin; the loop runs once, but you paid for the harness, the tool registry init, and the multi-turn context budget. Symptom: agent log shows zero tool calls, total runtime > 5× the pre-agency equivalent.
2. **Pipe-as-agent.** Pre-agency CLI wrapped in a hand-rolled bash loop that re-feeds output back as next-turn input, with `case` statements pattern-matching for "tool calls" in the model's text reply. Symptom: shell script > 80 lines, fragile parsers, no concept of structured tool results.
3. **Glue-script accretion around `llm`.** `llm` invoked from a script that grew `--system` flags, plugin chains, and output-format coercion until it implements a half-broken agent loop. Symptom: `wc -l` of the wrapper exceeds the cost of switching to an agent CLI.
4. **Mission-shaped one-shot.** Agent mission YAML for what is actually one prompt + one model reply, because that's the only orchestration the team knows. Symptom: mission has a single step, no branching, no tool list.
5. **Batch-as-agent-fleet.** N parallel agent CLIs for what is N independent one-shot transforms. Symptom: cost scales with N × harness overhead instead of N × token cost; cache hit rate is near zero because each agent boots a fresh context.

## How to use this template

1. Read the [`RUBRIC.md`](RUBRIC.md) once. It restates the five-clause rule with one diagnostic question per clause.
2. Drop [`prompts/classify.md`](prompts/classify.md) into your agent CLI as a prompt, *or* pipe a task description through it via `bin/classify.sh`.
3. The output is a structured recommendation: chosen class, named substrate (from your installed inventory), the clause that fired, and a confidence note.
4. Walk the [`examples/`](examples/) for three full traces — one per task shape — to calibrate.
5. **Adapt this section**: edit `bin/classify.sh` to point `INSTALLED_CLIS` at your actual installed CLI list and `AGENT_CMD` at the agent CLI you want to do the classification with.

## Adapt this section

```bash
# bin/classify.sh — top of file
INSTALLED_CLIS="${INSTALLED_CLIS:-llm,aichat,claude,codex,opencode}"   # your actual installed list
AGENT_CMD="${AGENT_CMD:-}"                                              # e.g. "llm -m gpt-4o-mini"; empty = dry-run
DRY_RUN_ON_NO_AGENT=1                                                   # 1 = exit 0 with the prompt printed; 0 = error out
```

If you don't set `AGENT_CMD`, the script prints the assembled prompt and exits 0. This is the dry-run mode and is intentional — it lets you eyeball the prompt before wiring it into a real agent.

## What ships in this directory

- `README.md` — this file
- `RUBRIC.md` — the five-clause decision rule, restated as one question per clause with a tiebreaker
- `prompts/classify.md` — LLM prompt that takes a task description + installed-CLI list and emits a structured recommendation
- `bin/classify.sh` — wrapper that pipes a task description through the prompt, dry-run-safe with no agent configured
- `examples/01-summarize-pr.md` — pre-agency case (clause 3 fires)
- `examples/02-fix-failing-tests.md` — agent case (clause 2 fires)
- `examples/03-extract-entities-from-emails.md` — batch case (clause 4 fires)

## Related templates

- [`reverse-engineer-cli`](../reverse-engineer-cli/) — once you've picked an agent CLI for an opaque target, this is the methodology you run inside it.
- [`scout-then-act-mission`](../scout-then-act-mission/) — for agent-class tasks, this is the mission shape to start with.
- [`failure-mode-catalog`](../failure-mode-catalog/) — substrate-mismatch failures often surface as `Tool-call Storm`, `Cache Prefix Thrash`, or `Continuation Loop`.

## Provenance

Derived from the synthesis post on pre-agency-LLM-CLIs vs agent-CLIs as a taxonomic split (`ai-native-notes`, 2026-04-24), itself built on the `ai-cli-zoo` 20-entry inventory and the morning's `llm`+`aichat` additions. The matrix's task→class rows come from concrete tasks shipped through this dispatcher in the last 60 ticks; the failure modes from observing the same five mistakes recur across that window.
