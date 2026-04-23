"""
Cache-aware request assembly for Google Gemini.

Gemini supports two caching modes:

  1. *Implicit* context caching: automatic, no API surface, requires
     the same byte-stable prefix discipline as OpenAI. Free, opt-out.
  2. *Explicit* context caching via CachedContent: you upload a chunk
     of context once, get back a handle, and reference it on every
     subsequent request. Useful when the long-lived context is large
     (e.g., a whole repo overview) and would otherwise be re-sent.

Tested against google-genai>=0.3.0.
"""

from google import genai
from google.genai import types

client = genai.Client()  # uses GEMINI_API_KEY


# ----- Mode 1: implicit caching via stable prefix -----

def build_request_implicit(
    system_prompt: str,
    long_lived_context: str,
    mission_state: list,
    current_turn: str,
):
    """
    Same canonical layout as the OpenAI snippet. Discipline is on the
    CALLER to keep every region above 'current_turn' byte-stable.
    Implicit cache hits show up in usage_metadata.cached_content_token_count.
    """
    contents = []
    contents.append(types.Content(role="user", parts=[types.Part(text=long_lived_context)]))
    for e in mission_state:
        contents.append(types.Content(role=e["role"], parts=[types.Part(text=e["text"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=current_turn)]))

    return dict(
        model="gemini-2.5-pro",  # ADAPT
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )


# ----- Mode 2: explicit cached content for large long-lived context -----

def create_explicit_cache(system_prompt: str, long_lived_context: str, ttl_sec: int = 3600):
    """
    Upload long_lived_context once. Returns a cache handle to reuse.
    Recommended when long_lived_context > 32k tokens AND will be reused
    in >= 2 requests.
    """
    cache = client.caches.create(
        model="gemini-2.5-pro",
        config=types.CreateCachedContentConfig(
            system_instruction=system_prompt,
            contents=[
                types.Content(role="user", parts=[types.Part(text=long_lived_context)])
            ],
            ttl=f"{ttl_sec}s",
        ),
    )
    return cache.name  # pass to build_request_explicit


def build_request_explicit(cache_name: str, mission_state: list, current_turn: str):
    contents = []
    for e in mission_state:
        contents.append(types.Content(role=e["role"], parts=[types.Part(text=e["text"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=current_turn)]))

    return dict(
        model="gemini-2.5-pro",
        contents=contents,
        config=types.GenerateContentConfig(cached_content=cache_name),
    )


if __name__ == "__main__":
    req = build_request_implicit(
        system_prompt="You are a careful code reviewer. Cite file:line.",
        long_lived_context="<repo overview, charter, glossary>",
        mission_state=[{"role": "user", "text": "Turn 1: review PR #42."}],
        current_turn="Turn 2: now review PR #43.",
    )

    resp = client.models.generate_content(**req)
    um = resp.usage_metadata
    cached = getattr(um, "cached_content_token_count", 0) or 0
    total = um.prompt_token_count
    print(
        f"prompt={total} cached={cached} "
        f"hit_rate={(cached / total if total else 0):.0%} "
        f"output={um.candidates_token_count}"
    )
