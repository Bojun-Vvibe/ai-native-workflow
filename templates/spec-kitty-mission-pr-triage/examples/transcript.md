# Sample run transcript — pr-triage against anomalyco/opencode

Captured from a representative run. Token-level model output is paraphrased; the
phase boundaries, gates, and WP outcomes mirror what a real spec-kitty mission
emits.

```
$ spec-kitty mission run --mission ./mission.example.yaml --inputs ./examples/mission-inputs.yaml

[mission:pr-triage] starting
[phase:specify] writing charter.md
[phase:specify] gate=human awaiting confirmation
> y
[phase:specify] confirmed

[phase:plan] agent=architect (profile: prompts/architect.md)
[phase:plan] fetching open PRs from anomalyco/opencode
[phase:plan] fetched 20 open PRs; 4 skipped via skip_labels (needs:compliance)
[phase:plan] producing plan.md
[phase:plan] writing 16 work packages: WP-23965, WP-23927, WP-23910, ... + WP-aggregate
[phase:plan] gate=human awaiting confirmation
> y
[phase:plan] confirmed

[phase:tasks] agent=architect
[phase:tasks] decomposing 16 WPs (auto gate)
[phase:tasks] all WPs have tasks.md; proceeding

[phase:implement-review-loop] mode=parallel max_parallel=4
[WP-23965] implement: agent=reviewer
[WP-23965] fetching diff (179 +0, 3 files)
[WP-23965] classifying risk: small, scoped feature; touches packages/tui only
[WP-23965] drafting review note
[WP-23965] wrote reviews/PR-23965.md (recommendation: approve, confidence: medium)
[WP-23965] review: agent=critic
[WP-23965] checks: draft_addresses_recommended_action=PASS no_github_api_write_calls=PASS tone_matches_maintainer_voice=PASS
[WP-23965] approved (round 1)

[WP-23927] implement: agent=reviewer
[WP-23927] fetching diff (74 +2, 2 files)
[WP-23927] classifying risk: small but touches provider/bedrock — historically regression-prone
[WP-23927] drafting review note
[WP-23927] wrote reviews/PR-23927.md (recommendation: request-changes, confidence: high)
[WP-23927] review: agent=critic
[WP-23927] checks: all PASS
[WP-23927] approved (round 1)

[WP-23910] implement: agent=reviewer
[WP-23910] fetching diff (415 +87, 23 files)
[WP-23910] classifying risk: docs-only, but cross-file consistency check needed
[WP-23910] drafting review note
[WP-23910] wrote reviews/PR-23910.md (recommendation: comment, confidence: medium)
[WP-23910] review: agent=critic
[WP-23910] checks: tone_matches_maintainer_voice=FAIL (too prescriptive for docs review)
[WP-23910] re-entering implement with feedback (round 2)
[WP-23910] re-drafted reviews/PR-23910.md
[WP-23910] review: agent=critic
[WP-23910] checks: all PASS
[WP-23910] approved (round 2)

... (13 more WPs elided) ...

[phase:aggregate] agent=reviewer
[phase:aggregate] consuming reviews/PR-*.md (16 files)
[phase:aggregate] producing reviews/_queue.md sorted by recommendation + risk
[phase:aggregate] gate=human awaiting confirmation
> y
[phase:aggregate] confirmed

[mission:pr-triage] complete
  - 16 PRs triaged
  - 4 skipped (label filter)
  - 1 WP required 2 review rounds
  - 0 GitHub write calls (verified)
  - artifacts: reviews/_queue.md + reviews/PR-*.md
  - cache: 87% prefix hit rate across WPs

elapsed: 14m 22s
input tokens (sum): 2.3M (effective after cache: 312K)
output tokens (sum): 681K
```

## What to notice

- The mission emits a clear gate at every human checkpoint. Nothing proceeds silently.
- Every WP records its risk classification *before* drafting, so the recommendation has visible reasoning.
- The critic agent caught one tone mismatch and forced a rewrite. Rejection cycles are normal, not failure.
- The final report explicitly verifies `0 GitHub write calls` — this is the safety property the mission exists to enforce.
- Cache hit rate (87%) reflects the stable-prefix design: prompts and charter are identical across WPs; only PR-specific context rotates.
