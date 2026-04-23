"""
Cache-aware request assembly for OpenAI SDK.

OpenAI uses *automatic* prefix caching. There is no cache_control
directive — the provider hashes your prompt prefix and serves cached
prefixes when subsequent requests share them byte-for-byte.

Implications:
  - You do NOT mark breakpoints. The provider chooses them, in fixed
    block sizes (currently ~1024 tokens).
  - Your only lever is *prefix stability*. Anything that mutates above
    the bulk of your prompt nukes the cache.
  - Hit information is reported in usage.prompt_tokens_details.cached_tokens.

Tested against openai>=1.40.0.
"""

import json
from openai import OpenAI

client = OpenAI()  # uses OPENAI_API_KEY


def build_request(
    system_prompt: str,
    tool_defs: list,
    long_lived_context: str,
    mission_state: list,
    current_turn: str,
):
    """
    Same canonical 4-region layout as the Anthropic version, minus the
    explicit breakpoints. Discipline is in the CALLER ensuring every
    field above 'current_turn' is byte-stable across turns.
    """
    # Deterministic tool serialization — sort keys so dict iteration
    # order can never shift the prefix bytes.
    tools_serialized = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": json.loads(json.dumps(t["parameters"], sort_keys=True)),
            },
        }
        for t in tool_defs
    ]

    messages = [
        {"role": "system", "content": system_prompt},
        # Long-lived context as a system message keeps it in the
        # cacheable region above the conversation tail.
        {"role": "system", "content": long_lived_context},
        # Mission state in order — the prior turns.
        *[{"role": e["role"], "content": e["text"]} for e in mission_state],
        # Current turn — the only fresh content.
        {"role": "user", "content": current_turn},
    ]

    return dict(
        model="gpt-4.1",  # ADAPT — pick a model that supports prefix caching
        messages=messages,
        tools=tools_serialized,
    )


# ----- Example invocation + cache-hit reporting -----

if __name__ == "__main__":
    req = build_request(
        system_prompt="You are a careful code reviewer. Always cite file:line.",
        tool_defs=[
            {
                "name": "read_file",
                "description": "Read a file from the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
        long_lived_context="<repo overview, charter, glossary — deterministic>",
        mission_state=[
            {"role": "user", "text": "Turn 1: review PR #42."},
            {"role": "assistant", "text": "Reviewed. 3 findings: ..."},
        ],
        current_turn="Turn 2: now review PR #43.",
    )

    resp = client.chat.completions.create(**req)

    usage = resp.usage
    cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) if hasattr(usage, "prompt_tokens_details") else 0
    print(
        f"prompt={usage.prompt_tokens} "
        f"cached={cached} "
        f"hit_rate={cached / usage.prompt_tokens:.0%} "
        f"completion={usage.completion_tokens}"
    )
