#!/usr/bin/env python3
"""Detect Grafana Tempo configurations from LLM output that disable
multi-tenancy on a deployment that is otherwise serving multiple
producers/consumers.

Tempo's ``multitenancy_enabled`` knob (under the top-level
``multitenancy_enabled:`` key, or its newer location under
``multitenancy_enabled`` in ``server`` / ``distributor`` blocks
depending on the version) defaults to ``false``. When it's false,
**every trace lands in the synthetic ``single-tenant`` tenant** and
the ``X-Scope-OrgID`` header from clients is ignored. LLMs commonly
copy the upstream "single-binary quickstart" verbatim into a
shared deployment, with the result that:

- traces from different teams/products co-mingle in one TSDB,
- per-tenant retention / rate-limit overrides silently no-op,
- queriers cannot enforce tenant isolation on read-back.

This detector flags four orthogonal regressions in the same YAML:

  1. ``multitenancy_enabled: false`` (or ``no`` / ``0`` / ``off``)
     explicitly set.
  2. ``multitenancy_enabled`` absent AND an ``overrides:`` /
     ``per_tenant_override_config:`` block is present (operator
     expects multi-tenancy but Tempo will not honour it).
  3. ``auth_enabled: false`` set (Tempo's older alias; same
     semantic effect — single-tenant mode).
  4. A ``distributor:`` block with multiple ``receivers:`` *and*
     no multi-tenancy enable (deployment is clearly fan-in but
     traces will collapse into one tenant).

Suppression: a top-level ``# tempo-single-tenant-ok`` comment in
the YAML disables all rules (single-team / lab deployment).

Public API:
    detect(text: str) -> bool
        True iff at least one finding fires.
    scan(text: str) -> list[tuple[int, str]]
        Returns (line, reason) tuples; empty == clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*tempo-single-tenant-ok", re.IGNORECASE)

# YAML key matchers (loose: tolerate quoting, trailing comments, indent).
_MT_LINE = re.compile(
    r"""(?im)^[\t ]*multitenancy_enabled[\t ]*:[\t ]*
        (?P<val>"[^"]*"|'[^']*'|[^\s#]+)""",
    re.VERBOSE,
)
_AUTH_LINE = re.compile(
    r"""(?im)^[\t ]*auth_enabled[\t ]*:[\t ]*
        (?P<val>"[^"]*"|'[^']*'|[^\s#]+)""",
    re.VERBOSE,
)
_OVERRIDES_BLOCK = re.compile(
    r"(?im)^[\t ]*(overrides|per_tenant_override_config)[\t ]*:",
)
_DISTRIBUTOR_BLOCK = re.compile(r"(?im)^[\t ]*distributor[\t ]*:")
_RECEIVERS_BLOCK = re.compile(r"(?im)^[\t ]*receivers[\t ]*:")
# count receivers as direct children: jaeger / otlp / zipkin / opencensus / kafka
_RECEIVER_KIND = re.compile(
    r"(?im)^[\t ]+(jaeger|otlp|zipkin|opencensus|kafka)[\t ]*:",
)

FALSE_VALUES = {"false", "no", "0", "off"}
TRUE_VALUES = {"true", "yes", "1", "on"}


def _strip(v: str) -> str:
    return v.strip().strip("'\"")


def _line_of(text: str, match: re.Match) -> int:
    return text.count("\n", 0, match.start()) + 1


def scan(text: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(text):
        return []
    findings: List[Tuple[int, str]] = []

    mt_match = _MT_LINE.search(text)
    auth_match = _AUTH_LINE.search(text)
    has_overrides = _OVERRIDES_BLOCK.search(text) is not None

    mt_value = _strip(mt_match.group("val")) if mt_match else None
    auth_value = _strip(auth_match.group("val")) if auth_match else None

    mt_is_false = mt_value is not None and mt_value.lower() in FALSE_VALUES
    mt_is_true = mt_value is not None and mt_value.lower() in TRUE_VALUES
    auth_is_false = auth_value is not None and auth_value.lower() in FALSE_VALUES
    auth_is_true = auth_value is not None and auth_value.lower() in TRUE_VALUES

    multitenancy_on = mt_is_true or auth_is_true

    # Rule 1
    if mt_is_false:
        findings.append(
            (
                _line_of(text, mt_match),
                "multitenancy_enabled: false — every trace lands in the "
                "synthetic 'single-tenant' tenant; X-Scope-OrgID is ignored",
            )
        )

    # Rule 3
    if auth_is_false:
        findings.append(
            (
                _line_of(text, auth_match),
                "auth_enabled: false — legacy Tempo alias for single-tenant "
                "mode; per-tenant overrides will silently no-op",
            )
        )

    # Rule 2: overrides present but multi-tenancy not turned on
    if has_overrides and not multitenancy_on:
        ov_match = _OVERRIDES_BLOCK.search(text)
        findings.append(
            (
                _line_of(text, ov_match),
                "overrides/per_tenant_override_config block present but "
                "multitenancy_enabled is not true — per-tenant limits will "
                "not be enforced",
            )
        )

    # Rule 4: multi-receiver distributor without multi-tenancy
    dist_match = _DISTRIBUTOR_BLOCK.search(text)
    if dist_match and not multitenancy_on:
        # find receivers: block under distributor (heuristic: next receivers:
        # after the distributor: line, in the same file).
        rcv_match = _RECEIVERS_BLOCK.search(text, dist_match.end())
        if rcv_match:
            # count receiver kinds in the slice immediately following
            # receivers:; stop at the next top-level (column-0) key.
            tail = text[rcv_match.end():]
            # cut at next top-level key (line starting with a non-space
            # alpha char followed by colon).
            cut = re.search(r"(?m)^[A-Za-z_][A-Za-z0-9_]*:", tail)
            slice_ = tail[: cut.start()] if cut else tail
            kinds = {m.group(1).lower() for m in _RECEIVER_KIND.finditer(slice_)}
            if len(kinds) >= 2:
                findings.append(
                    (
                        _line_of(text, dist_match),
                        "distributor configured with multiple receiver kinds "
                        f"({sorted(kinds)}) but multitenancy_enabled is not "
                        "true — fan-in traffic will collapse into one tenant",
                    )
                )

    # de-dup, preserving order
    seen: set = set()
    unique: List[Tuple[int, str]] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)
    return unique


def detect(text: str) -> bool:
    """Return True iff the config has at least one misconfiguration."""
    return bool(scan(text))


def _scan_path(p: Path) -> int:
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"{p}:0:read-error: {exc}")
        return 0
    hits = scan(text)
    for line, reason in hits:
        print(f"{p}:{line}:{reason}")
    return 1 if hits else 0


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    n = 0
    for a in argv[1:]:
        n += _scan_path(Path(a))
    return min(255, n)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
