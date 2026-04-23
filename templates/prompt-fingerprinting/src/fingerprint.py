"""
Prompt fingerprinting.

A prompt package is a dict with these keys:
  - "model": str, provider's model id
  - "provider": str, e.g. "anthropic", "openai", "google"
  - "system": str, the system prompt text
  - "tools": list[ {"name": str, "description": str, "input_schema": dict} ]
  - "decoding": {"temperature": float, "top_p": float, "max_tokens": int}
  - "conversation_prefix": list[ {"role": str, "content": str} ]
       Truncate this yourself before fingerprinting; the cache
       breakpoint usually lives at a fixed turn count.

`fingerprint(pkg)` returns a fingerprint dict with two summary
hashes:
  - cache_hash:    whitespace-sensitive, captures everything that
                   affects whether a provider's prompt cache will
                   hit or miss.
  - semantic_hash: whitespace-normalized, ignores tool ordering,
                   captures intent. If cache_hash changes but
                   semantic_hash doesn't, you broke cache for no
                   functional reason — the most common drift case.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_WS_RE = re.compile(r"\s+")


def _h(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()[:12]


def _normalize_ws(s: str) -> str:
    return _WS_RE.sub(" ", s).strip()


def _hash_tool(t: dict, *, semantic: bool) -> str:
    name = t.get("name", "")
    desc = t.get("description", "")
    schema = t.get("input_schema", {})
    if semantic:
        desc = _normalize_ws(desc)
    blob = json.dumps(
        {"name": name, "description": desc, "input_schema": schema},
        sort_keys=True,
        separators=(",", ":"),
    )
    return _h(blob)


def fingerprint(pkg: dict[str, Any]) -> dict[str, Any]:
    model = pkg.get("model", "")
    provider = pkg.get("provider", "")
    system = pkg.get("system", "")
    tools = pkg.get("tools", [])
    decoding = pkg.get("decoding", {})
    convo = pkg.get("conversation_prefix", [])

    system_hash = _h(system)
    system_norm_hash = _h(_normalize_ws(system))

    # cache_hash respects tool order and whitespace.
    tools_blob_cache = json.dumps(
        [_hash_tool(t, semantic=False) for t in tools],
        separators=(",", ":"),
    )
    tools_hash_cache = _h(tools_blob_cache)
    # semantic_hash sorts tools by name and normalizes ws.
    tools_blob_semantic = json.dumps(
        sorted(_hash_tool(t, semantic=True) for t in tools),
        separators=(",", ":"),
    )
    tools_hash_semantic = _h(tools_blob_semantic)

    decoding_blob = json.dumps(decoding, sort_keys=True, separators=(",", ":"))
    decoding_hash = _h(decoding_blob)

    convo_blob = json.dumps(convo, separators=(",", ":"))
    convo_hash = _h(convo_blob)

    cache_hash = _h(
        f"{model}|{provider}|{system_hash}|{tools_hash_cache}|{decoding_hash}|{convo_hash}"
    )
    semantic_hash = _h(
        f"{model}|{provider}|{system_norm_hash}|{tools_hash_semantic}|{decoding_hash}"
    )

    return {
        "model": model,
        "provider": provider,
        "system_hash": system_hash,
        "system_len": len(system),
        "tools_hash": tools_hash_cache,
        "tool_names": [t.get("name", "") for t in tools],
        "decoding_hash": decoding_hash,
        "convo_hash": convo_hash,
        "cache_hash": cache_hash,
        "semantic_hash": semantic_hash,
    }


if __name__ == "__main__":
    import sys

    pkg = json.load(sys.stdin)
    print(json.dumps(fingerprint(pkg), indent=2))
