"""Diff two prompt fingerprints. Emits a structured drift report."""
from __future__ import annotations

from typing import Any


def _delta_int(a: int, b: int) -> str:
    if a == b:
        return f"{a} (unchanged)"
    sign = "+" if b > a else ""
    return f"{a} → {b} ({sign}{b - a})"


def diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = {"drift": False, "components": {}}

    def note(key: str, changed: bool, detail: str) -> None:
        report["components"][key] = {"changed": changed, "detail": detail}
        if changed:
            report["drift"] = True

    note("model", a.get("model") != b.get("model"),
         f"{a.get('model')} → {b.get('model')}" if a.get("model") != b.get("model") else "unchanged")
    note("provider", a.get("provider") != b.get("provider"),
         f"{a.get('provider')} → {b.get('provider')}" if a.get("provider") != b.get("provider") else "unchanged")

    sys_changed = a.get("system_hash") != b.get("system_hash")
    note("system_prompt", sys_changed,
         f"len {_delta_int(a.get('system_len', 0), b.get('system_len', 0))}; "
         + ("hash changed" if sys_changed else "hash unchanged"))

    tools_changed = a.get("tools_hash") != b.get("tools_hash")
    a_names = a.get("tool_names", [])
    b_names = b.get("tool_names", [])
    if tools_changed:
        added = [n for n in b_names if n not in a_names]
        removed = [n for n in a_names if n not in b_names]
        if not added and not removed and sorted(a_names) == sorted(b_names):
            detail = f"reordered (no schema change in name set): {a_names} → {b_names}"
        else:
            detail = f"names changed: +{added} -{removed}"
    else:
        detail = "unchanged"
    note("tools", tools_changed, detail)

    note("decoding", a.get("decoding_hash") != b.get("decoding_hash"),
         "changed" if a.get("decoding_hash") != b.get("decoding_hash") else "unchanged")

    cache_changed = a.get("cache_hash") != b.get("cache_hash")
    semantic_changed = a.get("semantic_hash") != b.get("semantic_hash")

    report["cache_hash"] = {
        "from": a.get("cache_hash"),
        "to": b.get("cache_hash"),
        "broken": cache_changed,
    }
    report["semantic_hash"] = {
        "from": a.get("semantic_hash"),
        "to": b.get("semantic_hash"),
        "broken": semantic_changed,
    }
    if cache_changed and not semantic_changed:
        report["verdict"] = "silent_cache_break"
    elif cache_changed and semantic_changed:
        report["verdict"] = "intentional_change"
    else:
        report["verdict"] = "no_drift"

    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = []
    if not report["drift"]:
        lines.append("NO DRIFT")
    else:
        lines.append("DRIFT DETECTED")
    for k, v in report["components"].items():
        marker = "  " if not v["changed"] else "* "
        lines.append(f"{marker}{k}: {v['detail']}")
    ch = report["cache_hash"]
    sh = report["semantic_hash"]
    lines.append("")
    lines.append(
        f"  cache_hash:    {ch['from']} → {ch['to']}   "
        + ("(cache prefix BROKEN — full re-prime expected)" if ch["broken"] else "(cache prefix preserved)")
    )
    lines.append(
        f"  semantic_hash: {sh['from']} → {sh['to']}   "
        + ("(intent CHANGED)" if sh["broken"] else "(same intent)")
    )
    lines.append("")
    lines.append(f"  verdict: {report['verdict']}")
    return "\n".join(lines)
