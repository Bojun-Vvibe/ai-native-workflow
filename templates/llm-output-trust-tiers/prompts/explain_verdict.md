# Prompt — explain a tier verdict to the operator

Given a verdict record from `classify_trust_tier.py`, produce a one-paragraph
human-readable explanation suitable for a review-queue UI.

Input (single JSON object on stdin):

```json
{
  "id": "out-D",
  "tier": "human_review",
  "reasons": ["repair_count:1", "canary_failed"]
}
```

Output (strict JSON, single object, no markdown fences, no prose
outside the JSON):

```json
{
  "id": "out-D",
  "headline": "Needs human review: canary failed and the model needed one repair turn.",
  "next_action": "A reviewer should compare this output against the canary baseline before applying.",
  "do_not_apply": true
}
```

Hard constraints:

1. `do_not_apply` MUST be `true` for `tier in {human_review, quarantine}`,
   `false` otherwise.
2. `headline` MUST mention each reason from `reasons` (translated into
   plain English), and only those reasons. Do not invent risks.
3. Do not recommend bypassing review. If the verdict is `quarantine`,
   `next_action` MUST point at a forensic / triage workflow, never an
   "apply with caution" path.
4. Output **only** the single JSON object.
