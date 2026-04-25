"""Worked example: feed four messy LLM outputs through the repair pass.

Each fixture mimics a real failure mode I've seen in production agent
output: code-fence wrapping, trailing commas + smart quotes, missing
required fields with schema defaults, and a wrong-type field that's
losslessly coercible.

Run:  python3 run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repair import repair  # noqa: E402


SCHEMA = {
    "type": "object",
    "required": ["repo", "verdict", "confidence", "follow_ups"],
    "additionalProperties": False,
    "properties": {
        "repo": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": ["approve", "request_changes", "comment"],
            "default": "comment",
        },
        "confidence": {"type": "number"},
        "follow_ups": {
            "type": "array",
            "items": {"type": "string"},
        },
        "is_blocking": {"type": "boolean", "default": False},
    },
}

FIXTURES = [
    (
        "fenced_with_preamble",
        '''Sure, here is the review:

```json
{
  "repo": "acme-ci/runner",
  "verdict": "approve",
  "confidence": 0.82,
  "follow_ups": ["bump retry budget", "add trace id"]
}
```''',
    ),
    (
        "smart_quotes_and_trailing_commas",
        '{\u201crepo\u201d: \u201cacme-ci/runner\u201d, '
        '\u201cverdict\u201d: \u201crequest_changes\u201d, '
        '"confidence": 0.41, "follow_ups": ["fix flaky test",],}',
    ),
    (
        "missing_required_with_default",
        '{"repo": "acme-ci/runner", "confidence": 0.55, '
        '"follow_ups": [], "extra_chatter": "ignore me"}',
    ),
    (
        "type_mismatch_coercible",
        '{"repo": "acme-ci/runner", "verdict": "comment", '
        '"confidence": "0.73", "follow_ups": ["look at flake rate"], '
        '"is_blocking": "false"}',
    ),
    (
        "irrecoverable_missing_required",
        '{"verdict": "approve", "confidence": 0.9, "follow_ups": []}',
    ),
]


def main() -> int:
    accepted = 0
    quarantined = 0
    for name, raw in FIXTURES:
        print(f"--- {name} ---")
        res = repair(raw, SCHEMA)
        print(f"  ok={res.ok}")
        print(f"  repairs={res.repairs}")
        print(f"  violations={res.violations}")
        if res.value is not None:
            print(f"  value={json.dumps(res.value, sort_keys=True)}")
        if res.ok:
            accepted += 1
        else:
            quarantined += 1
        print()

    print(f"summary: {accepted} accepted, {quarantined} quarantined "
          f"out of {len(FIXTURES)} fixtures")

    # Self-check: lock in the contract.
    r1 = repair(FIXTURES[0][1], SCHEMA)
    assert r1.ok, r1.violations
    assert "strip_code_fence" in r1.repairs
    assert "strip_conversational_preamble" in r1.repairs

    r2 = repair(FIXTURES[1][1], SCHEMA)
    assert r2.ok, r2.violations
    assert "normalize_smart_quotes" in r2.repairs
    assert "strip_trailing_commas" in r2.repairs

    r3 = repair(FIXTURES[2][1], SCHEMA)
    assert r3.ok, r3.violations
    assert any(rep.startswith("default_required:") for rep in r3.repairs)
    assert any(rep.startswith("drop_additional:") for rep in r3.repairs)
    assert r3.value["verdict"] == "comment"

    r4 = repair(FIXTURES[3][1], SCHEMA)
    assert r4.ok, r4.violations
    assert r4.value["confidence"] == 0.73
    assert r4.value["is_blocking"] is False

    r5 = repair(FIXTURES[4][1], SCHEMA)
    assert not r5.ok
    assert any(v.startswith("missing_required:/repo") for v in r5.violations)
    print("self-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
