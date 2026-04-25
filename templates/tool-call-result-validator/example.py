"""End-to-end demo: 4 tool results passed through the validator.

Schema describes the contract for a hypothetical `lookup_user` tool that returns
{user_id: int, name: str, email: str}. We feed in 4 realistic LLM-shaped results.
"""

from validator import FieldSpec, ResultSchema, validate

SCHEMA = ResultSchema(
    tool_name="lookup_user",
    fields=[
        FieldSpec("user_id", int, required=True, coerce=int),
        FieldSpec("name", str, required=True),
        FieldSpec("email", str, required=True),
        FieldSpec("nickname", str, required=False),
    ],
    allow_extra=False,
)

CASES = [
    ("ok", {"user_id": 42, "name": "Ada", "email": "ada@example.com"}),
    ("extra_field", {"user_id": 7, "name": "Bo", "email": "bo@example.com", "debug_token": "xyz"}),
    ("missing_required", {"user_id": 11, "name": "Cy"}),  # email missing
    ("type_coerced", {"user_id": "99", "name": "Di", "email": "di@example.com"}),  # str -> int
]


def main() -> None:
    print("=" * 60)
    print("tool-call-result-validator — worked example")
    print("=" * 60)
    for label, result in CASES:
        print(f"\n--- case: {label} ---")
        print(f"raw:    {result}")
        report, safe = validate(result, SCHEMA)
        print(report.render())
        print(f"safe-for-llm: {safe}")
    print("\n" + "=" * 60)
    print("Summary: 1 clean pass, 1 extra-stripped, 1 hard fail, 1 coerced.")
    print("=" * 60)


if __name__ == "__main__":
    main()
