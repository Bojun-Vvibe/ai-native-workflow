# SPEC — llm-output-trust-tiers

## Tiers (ordered, most to least trusted)

| tier | meaning | who runs it |
| --- | --- | --- |
| `auto_apply` | apply without human review | orchestrator |
| `shadow_apply` | apply but mark for sampling / async review | orchestrator + reviewer queue |
| `human_review` | block until a human signs off | review UI |
| `quarantine` | never apply; store for forensics | quarantine bucket |

## Evidence record (input)

| field | type | required | notes |
| --- | --- | --- | --- |
| `id` | string | yes | opaque |
| `schema_ok` | bool | yes-ish (default false → quarantine) | from validator layer |
| `repair_count` | int ≥ 0 | default 0 | how many repair turns the structured-output-repair-loop used |
| `source_class` | enum | default `fresh` | `pinned_eval` \| `cached_known` \| `fresh` |
| `blast_radius` | enum | default `irreversible` | `read_only` \| `reversible` \| `irreversible` |
| `canary_passed` | bool \| null | default null | result of an upstream canary check, null = not run |
| `override_tier` | tier \| null | optional | caller can only DEMOTE; promotion attempts are recorded but ignored |

## Verdict (output)

| field | type | notes |
| --- | --- | --- |
| `id` | string | echoed |
| `tier` | enum | one of TIERS |
| `reasons` | list[string] | human-readable demotion reasons; `["clean"]` if none fired |

## Routing rules (in order)

1. **Hard fails → quarantine**, regardless of overrides:
    - `schema_ok=false` → `quarantine` with reason `schema_invalid`.
    - `repair_count > 3` → `quarantine` with reason `repair_count_over_threshold:N`.
2. Start at `auto_apply`. The remaining rules can only **demote** (move toward quarantine), never promote.
3. `repair_count >= 1` → demote to `shadow_apply`.
4. `repair_count >= 2` → demote to `human_review`.
5. `source_class == "fresh"` → demote to `shadow_apply`.
6. `blast_radius == "irreversible"` → demote to `human_review`.
7. `blast_radius == "reversible"` AND (any prior demotion fired) → demote to `shadow_apply`.
8. `canary_passed == false` → demote to `human_review`.
9. Caller `override_tier` can only DEMOTE. Promotion attempts are recorded as `override_ignored_would_promote:T` and the rule-derived tier wins.

## Exit codes (CLI)

| code | meaning |
| --- | --- |
| 0 | every output landed in `auto_apply` or `shadow_apply` |
| 1 | at least one output requires `human_review` (no quarantine) |
| 2 | at least one output is `quarantined`, or input was malformed |

## Composition

- `agent-output-validation` and `structured-output-repair-loop` produce
  `schema_ok` / `repair_count`.
- `structured-error-taxonomy` is upstream: a `tool_bad_input` class on
  the model call should set `source_class=fresh` even if a cache lookup
  said hit.
- Quarantined outputs are still safe to export through
  `agent-trace-redaction-rules` for forensic review.
