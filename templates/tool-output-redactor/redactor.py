"""Deterministic redactor for tool outputs before they re-enter the model context.

Why this exists
---------------
A tool call that reads files, queries databases, or shells out can return text
containing secrets (API keys, tokens), PII (emails, phone numbers), or absolute
host paths that leak the operator's environment. Feeding that text *back into
the model* has three failure modes:

1. The model echoes the secret in its next turn, where it gets logged / shown.
2. The model "memorizes" host-specific paths and uses them as if they were
   universally valid, breaking portability.
3. PII enters the eval / trace store, creating a compliance problem.

This redactor runs *between* the tool result and the model's next prompt. It is:

- **Deterministic.** Same input -> same output, byte for byte. Safe to use in
  prompt-cache key derivation.
- **Stable-mapped.** Each distinct secret/email/path gets a stable token like
  `<SECRET_1>` so the model can still reason about "the same value appeared
  twice" without ever seeing it.
- **Per-call scoped by default.** The token map resets per call. Use
  `Redactor(persistent=True)` to keep mappings stable across a whole session
  (useful when the same DB hostname legitimately recurs).
- **Stdlib only.** No regex packages, no PII libraries with surprise updates.

Patterns are intentionally conservative: false positives (over-redacting) are
preferred to false negatives (leaking). Add domain-specific patterns via
`Redactor(extra_patterns=[...])`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Pattern, Tuple


# Order matters: longer / more specific patterns first so they win over generic
# ones (e.g. AWS key prefix match before "long alnum string").
_DEFAULT_PATTERNS: List[Tuple[str, str]] = [
    # AWS access key id  (AKIA / ASIA + 16 uppercase alnum)
    ("AWS_KEY", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # GitHub fine-grained / classic PAT
    ("GITHUB_TOKEN", r"\bghp_[A-Za-z0-9]{36}\b"),
    ("GITHUB_TOKEN", r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
    # Generic "Bearer <token>" header value
    ("BEARER", r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{20,}"),
    # JWT (three base64url segments)
    ("JWT", r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    # Email address (intentionally simple — false positives ok)
    ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    # Absolute POSIX home path  (/Users/<name>/... or /home/<name>/...)
    ("HOME_PATH", r"/(?:Users|home)/[A-Za-z0-9_\-.]+(?:/[^\s'\"`]*)?"),
    # IPv4 (excluding obvious loopback/private-but-non-sensitive defaults)
    ("IPV4", r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)"
             r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
]


@dataclass
class RedactionReport:
    """Returned alongside the redacted text so callers can audit what was hit."""
    counts_by_kind: Dict[str, int] = field(default_factory=dict)
    total_redactions: int = 0

    def __str__(self) -> str:
        if self.total_redactions == 0:
            return "RedactionReport(none)"
        parts = [f"{k}={v}" for k, v in sorted(self.counts_by_kind.items())]
        return f"RedactionReport(total={self.total_redactions}, {', '.join(parts)})"


class Redactor:
    """Deterministic redactor with stable token mapping."""

    def __init__(
        self,
        extra_patterns: List[Tuple[str, str]] | None = None,
        persistent: bool = False,
    ) -> None:
        self._patterns: List[Tuple[str, Pattern[str]]] = [
            (kind, re.compile(rx)) for kind, rx in _DEFAULT_PATTERNS
        ]
        if extra_patterns:
            self._patterns.extend((k, re.compile(rx)) for k, rx in extra_patterns)
        self._persistent = persistent
        # token map: original-string -> stable label like "<EMAIL_1>"
        self._token_map: Dict[str, str] = {}
        self._counters: Dict[str, int] = {}

    def _next_label(self, kind: str) -> str:
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return f"<{kind}_{self._counters[kind]}>"

    def _label_for(self, kind: str, match: str) -> str:
        # Stable across reappearances within scope (always within a call;
        # across calls only if persistent=True).
        if match in self._token_map:
            return self._token_map[match]
        label = self._next_label(kind)
        self._token_map[match] = label
        return label

    def redact(self, text: str) -> Tuple[str, RedactionReport]:
        """Return (redacted_text, report). Idempotent on already-redacted text."""
        if not self._persistent:
            self._token_map = {}
            self._counters = {}

        report = RedactionReport()
        out = text
        for kind, rx in self._patterns:
            def _sub(m: re.Match[str], _kind: str = kind) -> str:
                report.counts_by_kind[_kind] = report.counts_by_kind.get(_kind, 0) + 1
                report.total_redactions += 1
                return self._label_for(_kind, m.group(0))
            out = rx.sub(_sub, out)
        return out, report
