"""
Provider-agnostic cache-hit instrumentation.

Wraps a request-builder + client-call pair, logs per-turn cache stats
to a JSONL file you can chart later. Supports Anthropic, OpenAI, and
Gemini response shapes.

Usage:

    from cache_hit_instrument import logged_call, summarize

    resp, stats = logged_call(
        provider="anthropic",
        client=anthropic_client,
        request=req,
        log_path="cache-stats.jsonl",
        turn_id=42,
    )

    # Later:
    summarize("cache-stats.jsonl")
"""

from __future__ import annotations
import json
import time
from pathlib import Path


def _extract_anthropic(resp) -> dict:
    u = resp.usage
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    fresh = u.input_tokens
    total_input = fresh + cache_read + cache_write
    return dict(
        input_total=total_input,
        cache_read=cache_read,
        cache_write=cache_write,
        fresh=fresh,
        output=u.output_tokens,
        hit_rate=(cache_read / total_input) if total_input else 0.0,
    )


def _extract_openai(resp) -> dict:
    u = resp.usage
    cached = 0
    if hasattr(u, "prompt_tokens_details") and u.prompt_tokens_details is not None:
        cached = getattr(u.prompt_tokens_details, "cached_tokens", 0) or 0
    return dict(
        input_total=u.prompt_tokens,
        cache_read=cached,
        cache_write=0,             # OpenAI does not separately bill writes
        fresh=u.prompt_tokens - cached,
        output=u.completion_tokens,
        hit_rate=(cached / u.prompt_tokens) if u.prompt_tokens else 0.0,
    )


def _extract_gemini(resp) -> dict:
    um = resp.usage_metadata
    cached = getattr(um, "cached_content_token_count", 0) or 0
    total = um.prompt_token_count
    return dict(
        input_total=total,
        cache_read=cached,
        cache_write=0,
        fresh=total - cached,
        output=um.candidates_token_count,
        hit_rate=(cached / total) if total else 0.0,
    )


_EXTRACTORS = {
    "anthropic": _extract_anthropic,
    "openai": _extract_openai,
    "gemini": _extract_gemini,
}


def logged_call(provider: str, client, request: dict, log_path: str, turn_id):
    """Execute the request, log cache stats, return (response, stats)."""
    t0 = time.time()
    if provider == "anthropic":
        resp = client.messages.create(**request)
    elif provider == "openai":
        resp = client.chat.completions.create(**request)
    elif provider == "gemini":
        resp = client.models.generate_content(**request)
    else:
        raise ValueError(f"unknown provider: {provider}")
    elapsed = time.time() - t0

    stats = _EXTRACTORS[provider](resp)
    stats.update(provider=provider, turn_id=turn_id, elapsed_sec=round(elapsed, 3))

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(stats) + "\n")

    return resp, stats


def summarize(log_path: str) -> dict:
    """Aggregate a JSONL log into a per-provider summary."""
    rows = [json.loads(l) for l in Path(log_path).read_text().splitlines() if l.strip()]
    if not rows:
        return {}
    by_prov = {}
    for r in rows:
        d = by_prov.setdefault(r["provider"], dict(turns=0, input=0, cache_read=0, output=0))
        d["turns"] += 1
        d["input"] += r["input_total"]
        d["cache_read"] += r["cache_read"]
        d["output"] += r["output"]
    for prov, d in by_prov.items():
        d["overall_hit_rate"] = (d["cache_read"] / d["input"]) if d["input"] else 0.0
    return by_prov


if __name__ == "__main__":
    import sys
    print(json.dumps(summarize(sys.argv[1]), indent=2))
