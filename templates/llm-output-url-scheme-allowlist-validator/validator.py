"""URL scheme allow-list validator for LLM output.

Pure stdlib. Scans LLM-emitted text for URLs and classifies any URL whose
scheme is not in the caller's allow-list. Findings carry the offending
scheme, the surface form of the URL, the byte offset where it was found,
and a `kind`:

  - `disallowed_scheme`   scheme present but not in allow-list
                          (e.g. `javascript:`, `file:`, `data:`, `vbscript:`)
  - `scheme_relative`     `//host/path` with no scheme — defers to the
                          renderer's current scheme, which is unsafe to
                          ship from an LLM that doesn't know the host page
  - `bare_host_https_likely`  text looks like `example.com/path` with no
                              scheme — flagged so the caller can decide
                              whether to auto-prefix `https://` or reject
  - `unicode_scheme`      ascii-fold mismatch in the scheme (e.g. a
                          full-width colon, or a Cyrillic letter inside
                          the scheme) — different finding from
                          `disallowed_scheme` because the surface form
                          may *look* allow-listed but isn't

The allow-list is a `frozenset[str]` of lower-cased scheme names. Defaults
to `{"https", "http", "mailto"}`. Findings are sorted by `(offset, kind,
url)` so two runs over the same input produce byte-identical output.

The detector is a pure function over a string; no I/O, no clocks, no
network. It does *not* fetch URLs or resolve DNS. It does not validate
that an `https://` URL actually exists — only that its *shape* is
allow-listed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import FrozenSet, List, Optional


DEFAULT_ALLOW: FrozenSet[str] = frozenset({"https", "http", "mailto"})

# Scheme is `[a-z][a-z0-9+\-.]*` per RFC 3986, then `:`. We match a wider
# class up front so we can flag unicode-scheme attacks as their own kind
# instead of silently failing to match.
_SCHEME_URL = re.compile(
    r"(?P<scheme>[A-Za-z\u0080-\uFFFF][A-Za-z0-9+\-.\u0080-\uFFFF]*)"
    r":(?P<rest>//[^\s<>\"')]+|[^\s<>\"')]+)"
)
# `//host/path` with no scheme — the leading `//` must not be inside an
# already-matched scheme URL, so we anchor on a non-letter-or-digit
# boundary.
_SCHEME_RELATIVE = re.compile(r"(?:^|(?<=[\s\(\[\"']))(//[A-Za-z0-9][^\s<>\"')]+)")
# Bare host-ish: `word.tld[/path]` with no scheme. Conservative — must
# have a `.` followed by 2+ ascii letters and at least one path char or
# end-of-token. We accept hyphens in the host. We deliberately do NOT
# match things like `version 1.2.3` (numeric tld) or `e.g.` (1-letter
# tld). Lower-cased compare against a tiny stop-set.
_BARE_HOST = re.compile(
    r"(?:^|(?<=[\s\(\[\"']))"
    r"(?P<host>(?:[A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,})"
    r"(?P<path>/[^\s<>\"')]*)?"
)
_BARE_HOST_STOP = frozenset({"e.g.", "i.e.", "vs.", "etc.", "et.al."})


class ValidationError(Exception):
    """Raised on malformed inputs (not on findings)."""


@dataclass(frozen=True)
class Finding:
    kind: str
    offset: int
    url: str
    scheme: Optional[str]


def _ascii_fold_scheme(scheme: str) -> str:
    """NFKD-fold a scheme to ASCII for the unicode-scheme check.

    Returns the folded lower-cased ASCII representation. If folding
    drops characters (i.e. the scheme contains code points with no
    ASCII compat), returns the empty string — caller treats that as
    `unicode_scheme`.
    """
    folded = unicodedata.normalize("NFKD", scheme)
    out_chars = []
    for ch in folded:
        if ord(ch) < 128:
            out_chars.append(ch)
    return "".join(out_chars).lower()


def validate_urls(
    text: str,
    allow: FrozenSet[str] = DEFAULT_ALLOW,
) -> List[Finding]:
    """Return a sorted list of findings for URLs in `text`.

    Args:
      text:  the raw LLM output to scan.
      allow: lower-cased scheme allow-list.

    Returns:
      List of `Finding` sorted by `(offset, kind, url)`. Empty list if
      every URL is allow-listed (or no URLs found).

    Raises:
      ValidationError: if `text` is not a string or `allow` is not a
                       `frozenset[str]` of lower-cased scheme names.
    """
    if not isinstance(text, str):
        raise ValidationError(f"text must be str, got {type(text).__name__}")
    if not isinstance(allow, frozenset):
        raise ValidationError(f"allow must be frozenset, got {type(allow).__name__}")
    for s in allow:
        if not isinstance(s, str) or s != s.lower() or not s:
            raise ValidationError(f"allow entries must be lower-cased non-empty str, got {s!r}")

    findings: List[Finding] = []
    consumed_offsets: List[range] = []  # avoid double-flagging

    # Pass 1: explicit-scheme URLs.
    for m in _SCHEME_URL.finditer(text):
        scheme_raw = m.group("scheme")
        offset = m.start()
        end = m.end()
        url = m.group(0)
        folded = _ascii_fold_scheme(scheme_raw)
        is_pure_ascii = all(ord(c) < 128 for c in scheme_raw)
        if not is_pure_ascii:
            # Unicode scheme — flag as its own kind. Note the folded
            # form might *match* the allow-list, but the surface form
            # is still suspect.
            findings.append(
                Finding(
                    kind="unicode_scheme",
                    offset=offset,
                    url=url,
                    scheme=scheme_raw,
                )
            )
            consumed_offsets.append(range(offset, end))
            continue
        scheme_l = scheme_raw.lower()
        if scheme_l not in allow:
            findings.append(
                Finding(
                    kind="disallowed_scheme",
                    offset=offset,
                    url=url,
                    scheme=scheme_l,
                )
            )
        consumed_offsets.append(range(offset, end))

    def _already_consumed(off: int) -> bool:
        for r in consumed_offsets:
            if off in r:
                return True
        return False

    # Pass 2: scheme-relative `//host/path`.
    for m in _SCHEME_RELATIVE.finditer(text):
        offset = m.start(1)
        end = m.end(1)
        if _already_consumed(offset):
            continue
        findings.append(
            Finding(
                kind="scheme_relative",
                offset=offset,
                url=m.group(1),
                scheme=None,
            )
        )
        consumed_offsets.append(range(offset, end))

    # Pass 3: bare hosts. Lowest priority — only flagged if not already
    # part of a scheme URL.
    for m in _BARE_HOST.finditer(text):
        offset = m.start()
        end = m.end()
        if _already_consumed(offset):
            continue
        host = m.group("host")
        path = m.group("path") or ""
        full = host + path
        if host.lower() in _BARE_HOST_STOP:
            continue
        # Skip pure version-like tokens: last label all digits.
        last_label = host.rsplit(".", 1)[-1]
        if last_label.isdigit():
            continue
        findings.append(
            Finding(
                kind="bare_host_https_likely",
                offset=offset,
                url=full,
                scheme=None,
            )
        )
        consumed_offsets.append(range(offset, end))

    findings.sort(key=lambda f: (f.offset, f.kind, f.url))
    return findings


def format_report(findings: List[Finding]) -> str:
    """Render findings as a deterministic plain-text report."""
    if not findings:
        return "OK: no disallowed URL schemes found.\n"
    lines = [f"FOUND {len(findings)} URL finding(s):"]
    for f in findings:
        scheme_part = f.scheme if f.scheme is not None else "-"
        lines.append(f"  [{f.kind}] offset={f.offset} scheme={scheme_part} url={f.url}")
    return "\n".join(lines) + "\n"
