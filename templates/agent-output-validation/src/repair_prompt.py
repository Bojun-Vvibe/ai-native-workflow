"""One-shot repair prompt template.

Pass `{error}`, `{schema}`, and `{original}` into a single LLM call.
Reject anything that comes back that doesn't validate. No second
chances; structural problems on a repair turn mean the sub-agent
prompt itself is wrong, not that you need another retry.
"""

REPAIR_PROMPT = """\
Your previous response did not satisfy the required output contract.

Error:
{error}

Required JSON Schema:
{schema}

Your previous response (verbatim):
{original}

Return ONLY a JSON object that satisfies the schema above. No prose,
no code fences, no explanation. If you cannot satisfy the schema with
the information you have, return:

{{"_unrecoverable": true, "reason": "<one short sentence>"}}
"""


def build_repair_prompt(error: str, schema: dict, original: str) -> str:
    import json

    return REPAIR_PROMPT.format(
        error=error,
        schema=json.dumps(schema, indent=2),
        original=original,
    )
