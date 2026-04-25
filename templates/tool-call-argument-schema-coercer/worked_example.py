"""
Worked example: feed five realistic LLM-emitted tool-call argument
dicts through the coercer and print what happened to each one.

Tool: schedule_followup(user_id: int, when_epoch: epoch_seconds,
                        urgent: bool, note: str = "", retries: int = 3)
"""

from coercer import coerce


SCHEMA = {
    "user_id":    {"type": "int", "required": True, "min": 1},
    "when_epoch": {"type": "epoch_seconds", "required": True},
    "urgent":     {"type": "bool", "required": True},
    "note":       {"type": "str", "required": False, "default": ""},
    "retries":    {"type": "int", "required": False, "default": 3,
                   "min": 0, "max": 10},
}


CASES = [
    ("clean call", {
        "user_id": 4421,
        "when_epoch": 1735689600,
        "urgent": True,
        "note": "renew profile",
    }),
    ("string ints + ISO date + stringified bool", {
        "user_id": "4421",
        "when_epoch": "2025-01-01T00:00:00Z",
        "urgent": "yes",
        "note": "renew profile",
        "retries": "5",
    }),
    ("nulls take defaults; missing optional omitted", {
        "user_id": 7,
        "when_epoch": 1700000000,
        "urgent": False,
        "note": None,        # -> default ""
        # retries missing -> default 3
    }),
    ("retries above max + unknown field", {
        "user_id": 7,
        "when_epoch": 1700000000,
        "urgent": False,
        "retries": 99,
        "phantom_field": "ignored at coerce, surfaced for repair",
    }),
    ("required missing + non-numeric string", {
        # user_id missing
        "when_epoch": "not-a-date",
        "urgent": "maybe",
    }),
]


def main() -> None:
    pass_count = 0
    fail_count = 0
    for label, args in CASES:
        result = coerce(SCHEMA, args)
        print(f"=== {label} ===")
        print(f"input:  {args}")
        if result.ok:
            pass_count += 1
            print(f"OK -> {result.args}")
            if result.coerced_fields:
                print(f"  coerced:   {result.coerced_fields}")
            if result.defaulted_fields:
                print(f"  defaulted: {result.defaulted_fields}")
            if result.unknown_fields:
                print(f"  unknown:   {result.unknown_fields}")
        else:
            fail_count += 1
            print("FAIL -> repair prompt for the model:")
            print(result.repair_prompt())
        print()

    print(f"summary: {pass_count} ok, {fail_count} need repair "
          f"(of {len(CASES)} total)")

    # Invariants
    assert pass_count == 3, "expected first three cases to coerce cleanly"
    assert fail_count == 2, "last two cases should fail and produce repair prompts"
    print("invariants OK")


if __name__ == "__main__":
    main()
