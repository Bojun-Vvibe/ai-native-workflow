"""Prompt version pinning manifest.

A lockfile-style manifest for the (system_prompt, user_prompt_template,
model, temperature, top_p, max_tokens, tool_signature) tuple that an
agent depends on. The manifest pins each tuple by SHA-256 hash. A
drift detector compares a live tuple against the pinned manifest and
emits a typed report listing exactly which fields drifted.

Stdlib only. Deterministic: the hash is computed over a canonical
JSON encoding (sorted keys, no whitespace, UTF-8).

Public API
----------
- canonicalize(tuple_dict) -> bytes
- fingerprint(tuple_dict) -> str  (hex sha256)
- build_manifest(entries) -> dict  (the lockfile)
- write_manifest(manifest, path) -> None
- load_manifest(path) -> dict
- detect_drift(manifest, name, live_tuple) -> DriftReport

Manifest schema (v1)
--------------------
{
  "schema_version": 1,
  "entries": {
    "<name>": {
      "fingerprint": "<hex>",
      "fields": ["system_prompt", "user_template", "model",
                 "temperature", "top_p", "max_tokens",
                 "tool_signature"],
      "tuple": { ... },
      "pinned_at": "<iso8601>"
    }
  }
}
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1

# Fields that participate in the fingerprint. Order is irrelevant
# because we sort keys at canonicalization time, but we keep an
# explicit allow-list so callers can't smuggle arbitrary fields in
# and accidentally invalidate every pin.
PINNED_FIELDS = (
    "system_prompt",
    "user_template",
    "model",
    "temperature",
    "top_p",
    "max_tokens",
    "tool_signature",
)


def canonicalize(tuple_dict: Mapping[str, Any]) -> bytes:
    """Return the canonical bytes used for hashing.

    Only PINNED_FIELDS are considered. Missing fields default to
    None so the encoding is total. Unknown fields raise ValueError
    to prevent silent drift.
    """
    extra = set(tuple_dict) - set(PINNED_FIELDS)
    if extra:
        raise ValueError(f"unknown pinned fields: {sorted(extra)}")
    payload = {k: tuple_dict.get(k, None) for k in PINNED_FIELDS}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def fingerprint(tuple_dict: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonicalize(tuple_dict)).hexdigest()


def build_manifest(
    entries: Mapping[str, Mapping[str, Any]],
    now_iso: str,
) -> dict:
    """Build a manifest dict from {name: tuple_dict}.

    `now_iso` is injected (not read from the wall clock) so the
    manifest is reproducible in tests.
    """
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "entries": {},
    }
    for name, t in entries.items():
        fp = fingerprint(t)
        out["entries"][name] = {
            "fingerprint": fp,
            "fields": list(PINNED_FIELDS),
            "tuple": {k: t.get(k, None) for k in PINNED_FIELDS},
            "pinned_at": now_iso,
        }
    return out


def write_manifest(manifest: Mapping[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


def load_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class DriftReport:
    name: str
    drifted: bool
    pinned_fingerprint: str
    live_fingerprint: str
    changed_fields: list[str] = field(default_factory=list)
    missing_in_live: list[str] = field(default_factory=list)
    unknown_in_live: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def detect_drift(
    manifest: Mapping[str, Any],
    name: str,
    live_tuple: Mapping[str, Any],
) -> DriftReport:
    if name not in manifest.get("entries", {}):
        raise KeyError(f"no pinned entry named {name!r}")
    entry = manifest["entries"][name]
    pinned_tuple = entry["tuple"]

    unknown = sorted(set(live_tuple) - set(PINNED_FIELDS))
    # We compute the live fingerprint over the allow-listed subset
    # so unknown extras don't cascade into a fingerprint mismatch
    # report; they are reported separately as `unknown_in_live`.
    live_subset = {k: live_tuple.get(k, None) for k in PINNED_FIELDS}
    live_fp = fingerprint(live_subset)

    changed = [
        k for k in PINNED_FIELDS
        if pinned_tuple.get(k) != live_subset.get(k)
    ]
    missing = [
        k for k in PINNED_FIELDS
        if k not in live_tuple and pinned_tuple.get(k) is not None
    ]

    return DriftReport(
        name=name,
        drifted=(live_fp != entry["fingerprint"]),
        pinned_fingerprint=entry["fingerprint"],
        live_fingerprint=live_fp,
        changed_fields=changed,
        missing_in_live=missing,
        unknown_in_live=unknown,
    )


def format_drift_report(report: DriftReport) -> str:
    lines = [f"drift report for {report.name!r}:"]
    lines.append(f"  drifted: {report.drifted}")
    lines.append(f"  pinned : {report.pinned_fingerprint[:16]}...")
    lines.append(f"  live   : {report.live_fingerprint[:16]}...")
    if report.changed_fields:
        lines.append(f"  changed_fields: {report.changed_fields}")
    if report.missing_in_live:
        lines.append(f"  missing_in_live: {report.missing_in_live}")
    if report.unknown_in_live:
        lines.append(f"  unknown_in_live: {report.unknown_in_live}")
    return "\n".join(lines)
