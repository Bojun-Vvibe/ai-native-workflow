"""
Token-budget tracker — the public surface is three functions:

    start_session(name, phase=None) -> session_id
    record(session_id, *, model, provider, usage, phase=None,
           tool=None, elapsed_sec=None, retry_of=None) -> None
    report(since_days=7, by=("model",)) -> str (markdown table)

The tracker writes one JSONL file per (month, session) under
~/.local/share/token-budget/<yyyy-mm>/<session-id>.jsonl. Cost is
computed at report time from prices.json so old logs re-cost
correctly when prices change.

Usage from inside an agent loop:

    from budget import start_session, record
    sid = start_session("review-mission-2026-04-23")
    resp = client.messages.create(**req)
    record(sid, model="claude-sonnet-4-5-20250929", provider="anthropic",
           usage=resp.usage, phase="review", tool=None)
"""

from __future__ import annotations
import json
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

LOG_ROOT = Path(os.environ.get(
    "TOKEN_BUDGET_ROOT",
    Path.home() / ".local" / "share" / "token-budget",
))


def _log_path(session_id: str) -> Path:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    p = LOG_ROOT / month / f"{session_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def start_session(name: str, phase: str | None = None) -> str:
    """Allocate and return a session id. The id encodes the session name
    so log files are human-grepable."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    sid = f"{safe}-{uuid.uuid4().hex[:8]}"
    return sid


def _normalize_usage(provider: str, usage) -> dict:
    """Return a flat dict with input_total / cache_read / cache_write /
    fresh_input / output regardless of provider shape."""
    if provider == "anthropic":
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        fresh = usage.input_tokens
        return dict(
            input_total=fresh + cache_read + cache_write,
            cache_read=cache_read,
            cache_write=cache_write,
            fresh_input=fresh,
            output=usage.output_tokens,
        )
    if provider == "openai":
        cached = 0
        if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        return dict(
            input_total=usage.prompt_tokens,
            cache_read=cached,
            cache_write=0,
            fresh_input=usage.prompt_tokens - cached,
            output=usage.completion_tokens,
        )
    if provider == "gemini":
        cached = getattr(usage, "cached_content_token_count", 0) or 0
        total = usage.prompt_token_count
        return dict(
            input_total=total,
            cache_read=cached,
            cache_write=0,
            fresh_input=total - cached,
            output=usage.candidates_token_count,
        )
    raise ValueError(f"unknown provider: {provider}")


def record(
    session_id: str,
    *,
    model: str,
    provider: str,
    usage,
    phase: str | None = None,
    tool: str | None = None,
    elapsed_sec: float | None = None,
    retry_of: str | None = None,
) -> None:
    """Append one event to the session log."""
    norm = _normalize_usage(provider, usage)
    entry = dict(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        session_id=session_id,
        phase=phase,
        tool=tool,
        model=model,
        provider=provider,
        elapsed_sec=elapsed_sec,
        retry_of=retry_of,
        **norm,
    )
    with open(_log_path(session_id), "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- reporting ----------

def _load_prices() -> dict:
    here = Path(__file__).parent
    return json.loads((here / "prices.json").read_text())


def _cost(entry: dict, prices: dict) -> float:
    """Compute USD cost for one entry from prices.json."""
    p = prices.get(entry["model"])
    if not p:
        return 0.0
    cr = entry.get("cache_read", 0) * p.get("cache_read_per_mtok", 0) / 1e6
    cw = entry.get("cache_write", 0) * p.get("cache_write_per_mtok", p.get("input_per_mtok", 0)) / 1e6
    fi = entry.get("fresh_input", entry["input_total"]) * p.get("input_per_mtok", 0) / 1e6
    out = entry["output"] * p.get("output_per_mtok", 0) / 1e6
    return cr + cw + fi + out


def _iter_recent_entries(since_days: int) -> Iterable[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    if not LOG_ROOT.exists():
        return
    for jsonl in LOG_ROOT.rglob("*.jsonl"):
        try:
            for line in jsonl.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    yield entry
        except (json.JSONDecodeError, KeyError, ValueError):
            continue


def report(since_days: int = 7, by: tuple = ("model",)) -> str:
    """Markdown table aggregating cost over the last N days, grouped by
    one or more dimensions ('model', 'phase', 'tool', 'session_id')."""
    prices = _load_prices()
    buckets: dict = defaultdict(lambda: dict(events=0, input=0, cache_read=0, output=0, cost=0.0))
    for e in _iter_recent_entries(since_days):
        key = tuple(e.get(dim) or "(none)" for dim in by)
        b = buckets[key]
        b["events"] += 1
        b["input"] += e.get("input_total", 0)
        b["cache_read"] += e.get("cache_read", 0)
        b["output"] += e.get("output", 0)
        b["cost"] += _cost(e, prices)

    if not buckets:
        return f"_No events in the last {since_days} days._"

    rows = sorted(buckets.items(), key=lambda kv: -kv[1]["cost"])
    headers = list(by) + ["events", "input", "cache_read", "hit_rate", "output", "cost_usd"]
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    total_cost = 0.0
    for key, b in rows:
        hit = (b["cache_read"] / b["input"]) if b["input"] else 0.0
        total_cost += b["cost"]
        lines.append("| " + " | ".join([
            *(str(k) for k in key),
            str(b["events"]),
            f"{b['input']:,}",
            f"{b['cache_read']:,}",
            f"{hit:.0%}",
            f"{b['output']:,}",
            f"${b['cost']:.2f}",
        ]) + " |")
    lines.append(f"\n**Total cost (last {since_days} days):** ${total_cost:.2f}")
    return "\n".join(lines)
