# Repair-turn template

This is the user-turn shape for attempt N>1 of the repair loop.
The loop assembles it from the original prompt, the previous
attempt's raw output, and the validator error.

---

{{ original_prompt }}

--- Previous attempt output ---
{{ prev_raw_output }}
--- End previous attempt ---

=== REPAIR REQUIRED ===
Previous attempt failed validation:
  path:     {{ json_pointer }}
  error:    {{ expected }}
  got:      {{ got }}
  fix:      {{ suggested_fix }}

Reproduce ALL fields from the previous attempt EXCEPT the one
above. Do not change other fields. Do not add explanatory prose.
=== END REPAIR ===

---

## Why "reproduce all fields except"

A common failure mode without that instruction: the model treats
the repair turn as a fresh generation, regenerates from scratch,
fixes the flagged field, and *introduces a new error in a
previously-fine field*. The loop then bounces between two
fingerprints, each one "fixing" what the other broke. With the
explicit "reproduce except" instruction this stops happening for
~all current frontier models.
