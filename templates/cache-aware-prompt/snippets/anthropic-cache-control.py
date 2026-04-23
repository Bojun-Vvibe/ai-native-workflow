"""
Cache-aware request assembly for Anthropic SDK.

Demonstrates explicit cache_control breakpoints in the canonical
4-region order: system, tools, long-lived context, mission state.

Anthropic charges:
  - cache write: 1.25x normal input price (first time a block is seen)
  - cache read:  0.10x normal input price (subsequent hits within TTL)

So a block needs ~3 hits to amortize the write cost.

Tested against anthropic-sdk-python >=0.34.0. Adapt model name and
budget for your account.
"""

from anthropic import Anthropic

client = Anthropic()  # uses ANTHROPIC_API_KEY


def build_request(
    system_prompt: str,
    tool_defs: list,
    long_lived_context: str,
    mission_state: list,
    current_turn: str,
):
    """
    Assemble a request with 4 cache breakpoints.

    All four arguments above 'current_turn' should be byte-stable across
    turns. The CALLER is responsible for that — see anti-patterns in
    the template README. This function only places the breakpoints.
    """
    return dict(
        model="claude-sonnet-4-5-20250929",  # ADAPT
        max_tokens=4096,
        # ----- [1] system prompt with breakpoint -----
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},  # BP-1
            }
        ],
        # ----- [2] tools (Anthropic caches tool defs together with system) -----
        tools=tool_defs,  # cache_control on system covers tools too
        # ----- [3] + [4] + [5] go in messages -----
        messages=[
            # Long-lived context as the first user message, with its own BP
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": long_lived_context,
                        "cache_control": {"type": "ephemeral"},  # BP-2
                    }
                ],
            },
            # Mission state: prior turns appended in order. Mark only the
            # LAST entry of mission_state for caching — Anthropic caches
            # everything up to the breakpoint.
            *_mission_state_to_messages(mission_state),
            # Current turn — never marked for cache (it's the fresh part)
            {"role": "user", "content": current_turn},
        ],
    )


def _mission_state_to_messages(mission_state: list) -> list:
    """Convert a list of {role, text} dicts into Anthropic messages,
    placing BP-3 on the final entry.
    """
    if not mission_state:
        return []
    msgs = []
    for i, entry in enumerate(mission_state):
        is_last = i == len(mission_state) - 1
        block = {"type": "text", "text": entry["text"]}
        if is_last:
            block["cache_control"] = {"type": "ephemeral"}  # BP-3
        msgs.append({"role": entry["role"], "content": [block]})
    return msgs


# ----- Example invocation -----

if __name__ == "__main__":
    req = build_request(
        system_prompt="You are a careful code reviewer. Always cite file:line.",
        tool_defs=[
            {
                "name": "read_file",
                "description": "Read a file from the workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ],
        long_lived_context="<repo overview, charter, glossary — assembled deterministically>",
        mission_state=[
            {"role": "user", "text": "Turn 1: review PR #42."},
            {"role": "assistant", "text": "Reviewed. 3 findings: ..."},
            {"role": "user", "text": "Turn 2: now review PR #43."},
            {"role": "assistant", "text": "Reviewed. 1 finding: ..."},
        ],
        current_turn="Turn 3: summarize the worst finding so far.",
    )

    resp = client.messages.create(**req)

    # Cache usage is reported on the response. See
    # snippets/cache-hit-instrument.py for a wrapper that logs it.
    usage = resp.usage
    print(
        f"input={usage.input_tokens} "
        f"cache_creation={getattr(usage, 'cache_creation_input_tokens', 0)} "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
        f"output={usage.output_tokens}"
    )
