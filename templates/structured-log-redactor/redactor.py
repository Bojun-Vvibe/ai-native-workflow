"""structured-log-redactor — recursive secret / PII redaction for JSON logs.

The post-hoc, log-pipeline-side companion of `prompt-pii-redactor`
(prompt-side) and `tool-output-redactor` (tool-output-side). This
template scrubs **already-recorded** JSONL log streams before they
leave the trust boundary they were written in: shipping to a SaaS log
backend, attaching to a bug report, exporting to a downstream
analytics warehouse.

Two complementary mechanisms, applied per-record:

* **key-name redaction** — any dict key whose name matches a
  case-insensitive `sensitive_keys` set is replaced wholesale with
  ``"<REDACTED:keyname>"``. The match is on the key the value is
  *bound to*, not on the value itself; this catches a 400-byte JWT
  written under ``"authorization"`` even though the token itself
  contains nothing pattern-matchable.
* **regex value redaction** — every string leaf is scanned with a
  pinned set of high-precision patterns (AWS access keys, GitHub PATs,
  Slack tokens, JWTs, RFC-5322-ish email, IPv4). Matches are replaced
  with a typed marker like ``"<REDACTED:aws_access_key>"`` so the
  redacted log is still human-skimmable for "which class of secret was
  here?" without leaking the value.

The walker is **structurally pure**: it returns a new object and never
mutates input. That matters because the caller often wants to keep the
unredacted record in memory (to retry an upload, to compare side-by-
side in a test) while writing only the redacted copy to disk.

Counter-intentional design choices:

* No "smart" PII detection. Name-detection / address-detection / ML
  classifiers are out of scope. They produce false positives that
  *change the meaning* of a log line (a function called ``Mark`` is
  not a person), and false negatives that lull the operator into
  trusting the redactor for things it cannot do. This template only
  redacts things with a high-precision shape.
* Numbers are never redacted by value. A 16-digit number can be a
  bank card or a build id; the redactor cannot tell. If you have
  numeric secrets, bind them to a sensitive *key* and let the
  key-name layer catch them.
* Booleans, ``None``, and non-string keys pass through untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Pattern


# ----------------------------------------------------------------------
# pinned high-precision patterns
#
# Every pattern is anchored by something stricter than [a-z]+ so a short
# innocuous string ("hello@") cannot trip it. The marker label is the
# only thing the redacted log retains about the original — never the
# original value, never a hash of it (a hash is a pre-image attack
# waiting for a known-shape secret).
# ----------------------------------------------------------------------
DEFAULT_PATTERNS: tuple[tuple[str, str], ...] = (
    # AWS access key id: starts with AKIA / ASIA / AGPA / AIDA / AROA /
    # AIPA / ANPA / ANVA / ASCA, then 16 uppercase-alnum.
    (
        "aws_access_key",
        r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)[A-Z0-9]{16}\b",
    ),
    # GitHub fine-grained / classic PATs.
    ("github_pat", r"\bghp_[A-Za-z0-9]{36}\b"),
    ("github_pat_fine_grained", r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
    # Slack bot/user/app/legacy token.
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    # JWT — three base64url segments separated by '.'.
    (
        "jwt",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    ),
    # RFC-5322-ish email. Deliberately tight: refuses single-letter TLDs.
    (
        "email",
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    ),
    # IPv4 address. (No IPv6: would over-match plain UUIDs / hex hashes.)
    (
        "ipv4",
        r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b",
    ),
)


DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "auth",
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "private_key",
        "ssh_key",
        "cookie",
        "set-cookie",
        "x-api-key",
        "session",
    }
)


@dataclass
class RedactionStats:
    records_processed: int = 0
    keys_redacted: dict[str, int] = field(default_factory=dict)
    patterns_redacted: dict[str, int] = field(default_factory=dict)


@dataclass
class StructuredLogRedactor:
    """Pure recursive redactor over JSON-shaped Python objects.

    ``redact(record)`` returns a new object with the same structural
    shape as ``record`` but with sensitive keys' values and matched
    string leaves replaced. Input is never mutated.
    """

    sensitive_keys: frozenset[str] = field(default_factory=lambda: DEFAULT_SENSITIVE_KEYS)
    patterns: tuple[tuple[str, Pattern[str]], ...] = field(init=False)
    raw_patterns: tuple[tuple[str, str], ...] = DEFAULT_PATTERNS
    stats: RedactionStats = field(default_factory=RedactionStats)

    def __post_init__(self) -> None:
        # Normalize sensitive_keys to lowercase for case-insensitive
        # comparison, and compile patterns once.
        object.__setattr__(
            self,
            "sensitive_keys",
            frozenset(k.lower() for k in self.sensitive_keys),
        )
        self.patterns = tuple(
            (label, re.compile(pat)) for label, pat in self.raw_patterns
        )

    # ------------------------------------------------------------------
    def redact(self, record: Any) -> Any:
        """Return a redacted *deep copy* of ``record``."""
        result = self._walk(record)
        self.stats.records_processed += 1
        return result

    def redact_lines(self, lines: Iterable[str]) -> Iterable[str]:
        """Stream-redact JSONL lines. Non-JSON lines are passed through
        untouched (a syslog-style mixed log is common in the wild).
        """
        import json

        for line in lines:
            stripped = line.rstrip("\n")
            if not stripped:
                yield line
                continue
            try:
                obj = json.loads(stripped)
            except (ValueError, TypeError):
                yield line
                continue
            yield json.dumps(self.redact(obj), sort_keys=True) + "\n"

    # ------------------------------------------------------------------
    def _walk(self, node: Any) -> Any:
        if isinstance(node, dict):
            out: dict[Any, Any] = {}
            for k, v in node.items():
                if isinstance(k, str) and k.lower() in self.sensitive_keys:
                    out[k] = f"<REDACTED:{k.lower()}>"
                    self.stats.keys_redacted[k.lower()] = (
                        self.stats.keys_redacted.get(k.lower(), 0) + 1
                    )
                    continue
                out[k] = self._walk(v)
            return out
        if isinstance(node, list):
            return [self._walk(x) for x in node]
        if isinstance(node, tuple):
            return tuple(self._walk(x) for x in node)
        if isinstance(node, str):
            return self._scan_string(node)
        # int / float / bool / None pass through.
        return node

    def _scan_string(self, value: str) -> str:
        result = value
        for label, pat in self.patterns:
            def _sub(_m, _label=label) -> str:
                self.stats.patterns_redacted[_label] = (
                    self.stats.patterns_redacted.get(_label, 0) + 1
                )
                return f"<REDACTED:{_label}>"

            result = pat.sub(_sub, result)
        return result
