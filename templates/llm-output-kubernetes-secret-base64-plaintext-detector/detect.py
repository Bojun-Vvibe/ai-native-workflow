#!/usr/bin/env python3
"""Detect Kubernetes Secret manifests committed with plaintext-equivalent data.

A `kind: Secret` manifest stores values base64-*encoded* (not
encrypted). Anyone who can read the YAML — every reviewer on
every PR, every CI log, every ``git log -p`` — can decode the
secret with one ``base64 -d``. LLMs nonetheless cheerfully emit
"production-ready" Secret manifests with real-looking
credentials base64'd into ``data:`` because the format
demands base64 and the model has no concept of "do not commit
this".

What this flags
---------------
* `k8s-secret-data-with-base64-secret` — a `kind: Secret`
  manifest whose `data:` map decodes to a value that:
  - matches a known credential prefix (`AKIA…`, `SK_LIVE_`,
    `xoxb-`, `ghp_`, `gho_`, `ghs_`, `ghu_`, `glpat-`,
    `AIza…`, `-----BEGIN … PRIVATE KEY-----`, `eyJ…`-shaped
    JWT), or
  - looks like a high-entropy password (>= 16 chars, mixed
    classes, not a placeholder).
* `k8s-secret-stringdata-with-secret` — same checks but applied
  to `stringData:` map values directly (no decode needed).
* `k8s-secret-data-undecodable-non-placeholder` — `data:` value
  is not valid base64 AND is not a placeholder; almost certainly
  someone forgot the ``base64`` step and pasted the plaintext
  raw, which `kubectl apply` will reject with a confusing error.

What this does NOT flag
-----------------------
* `Secret` manifests whose values decode to obvious placeholders
  (`changeme`, `replace_me`, `<…>`, `${…}`, `xxxxxx…`,
  `your-…`, all-same-char strings, single short word).
* Manifests that source secrets via `secretRef` /
  `valueFrom.secretKeyRef` / `envFrom.secretRef` (those don't
  embed the value).
* `SealedSecret`, `ExternalSecret`, `SecretStore`, `VaultAuth`,
  or other CRDs that exist precisely to *avoid* committing
  plaintext.
* Lines marked with a trailing `# k8s-secret-ok` comment.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `*.yaml`, `*.yml`. Multi-doc
YAML (``---`` separated) is supported.
"""
from __future__ import annotations

import base64
import binascii
import re
import sys
from pathlib import Path


SUFFIXES = {".yaml", ".yml"}

RE_SUPPRESS = re.compile(r"#\s*k8s-secret-ok\b")
RE_KIND_SECRET = re.compile(r"^\s*kind\s*:\s*['\"]?Secret['\"]?\s*(?:#.*)?$", re.IGNORECASE)
RE_API_VERSION = re.compile(r"^\s*apiVersion\s*:\s*['\"]?v1['\"]?\s*(?:#.*)?$")
RE_DATA_BLOCK = re.compile(r"^(\s*)data\s*:\s*(?:#.*)?$")
RE_STRINGDATA_BLOCK = re.compile(r"^(\s*)stringData\s*:\s*(?:#.*)?$")
# A scalar "key: value" inside data: — accept anything non-whitespace
# in value position; we then run base64 validation inside.
RE_DATA_SCALAR = re.compile(
    r"""^(\s*)([A-Za-z0-9._-]+)\s*:\s*(?:(['"])(.*?)\3|(\S[^#\n]*?))\s*(?:#.*)?$"""
)
# Wider value capture for stringData (anything until #-comment / EOL).
RE_STRINGDATA_SCALAR = re.compile(
    r"""^(\s*)([A-Za-z0-9._-]+)\s*:\s*(?:(['"])(.*?)\3|([^#\n]*?))\s*(?:#.*)?$"""
)
RE_DOC_SEP = re.compile(r"^---\s*(?:#.*)?$")

# Known credential prefixes that scream "real secret"
KNOWN_PREFIXES = (
    "AKIA", "ASIA",                      # AWS access key id
    "sk_live_", "sk_test_",              # Stripe (test fixtures use sk_test_FAKE)
    "rk_live_", "pk_live_",              # Stripe restricted/publishable
    "xoxb-", "xoxp-", "xoxa-", "xoxr-",  # Slack
    "ghp_", "gho_", "ghs_", "ghu_",      # GitHub PATs / OAuth
    "github_pat_",
    "glpat-",                            # GitLab PAT
    "AIza",                              # Google API key
    "ya29.",                             # Google OAuth access
    "AAAA",                              # FCM server key (4x A start)
    "SG.",                               # SendGrid
    "Bearer ",
)
RE_PEM_PRIVATE = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")
RE_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")

PLACEHOLDER_WORDS = (
    "changeme", "change_me", "replace", "placeholder", "example",
    "redacted", "dummy", "sample", "your_", "your-",
    "todo_replace", "fill_me", "fillme",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"^<[^>]+>$"),
    re.compile(r"^\$\{[^}]+\}$"),
    re.compile(r"^\{\{[^}]+\}\}$"),
    re.compile(r"^x{4,}$", re.IGNORECASE),
)
# Test-fixture FAKE marker (we use FAKE in our own bad fixtures
# but they're meant to *trigger* — we leverage the prefix only).


def looks_placeholder(decoded: str) -> bool:
    s = decoded.strip()
    if not s:
        return True
    low = s.lower()
    for w in PLACEHOLDER_WORDS:
        if w in low:
            return True
    for pat in PLACEHOLDER_PATTERNS:
        if pat.match(s):
            return True
    if len(s) >= 4 and len(set(s)) == 1:
        return True
    # Single short word, no symbols, all lowercase or all uppercase
    # → likely placeholder ("password", "secret", "admin").
    if len(s) <= 12 and re.fullmatch(r"[A-Za-z]+", s):
        if low in {"password", "secret", "admin", "user", "test",
                   "guest", "default", "root", "value", "foo", "bar",
                   "baz", "demo", "key", "token", "name"}:
            return True
    return False


def looks_high_entropy_password(s: str) -> bool:
    if len(s) < 16:
        return False
    classes = 0
    if re.search(r"[a-z]", s):
        classes += 1
    if re.search(r"[A-Z]", s):
        classes += 1
    if re.search(r"[0-9]", s):
        classes += 1
    if re.search(r"[^A-Za-z0-9]", s):
        classes += 1
    if classes < 3:
        return False
    # Reject if it's just a sentence with spaces ("this is a placeholder
    # password value here") — require unique-char ratio.
    uniq = len(set(s)) / len(s)
    if uniq < 0.35:
        return False
    return True


def matches_known_credential(decoded: str) -> str | None:
    s = decoded.strip()
    for pref in KNOWN_PREFIXES:
        if s.startswith(pref):
            return f"prefix:{pref!r}"
    if RE_PEM_PRIVATE.search(s):
        return "pem-private-key"
    if RE_JWT.match(s):
        return "jwt-shape"
    return None


def try_b64_decode(value: str) -> tuple[bool, str]:
    """Return (ok, decoded_text). Reject non-strict base64."""
    if not value:
        return False, ""
    # Standard base64 alphabet; allow `=` padding only at end.
    if not re.fullmatch(r"[A-Za-z0-9+/]+=*", value):
        return False, ""
    if len(value) % 4 != 0:
        return False, ""
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False, ""
    try:
        return True, raw.decode("utf-8")
    except UnicodeDecodeError:
        # Binary payload — could be a real key blob; treat as
        # non-text but still not a placeholder.
        return True, raw.decode("latin-1")


def split_docs(text: str):
    """Yield (doc_start_line, doc_text) for each YAML document."""
    lines = text.splitlines()
    cur_start = 1
    cur = []
    for i, raw in enumerate(lines, start=1):
        if RE_DOC_SEP.match(raw):
            if cur:
                yield cur_start, "\n".join(cur)
            cur = []
            cur_start = i + 1
        else:
            cur.append(raw)
    if cur:
        yield cur_start, "\n".join(cur)


def is_secret_doc(doc_text: str) -> bool:
    has_kind = False
    for raw in doc_text.splitlines():
        if RE_KIND_SECRET.match(raw):
            has_kind = True
            break
    return has_kind


def scan_secret_doc(path: Path, doc_start: int, doc_text: str):
    findings = []
    lines = doc_text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        raw = lines[i]
        m_data = RE_DATA_BLOCK.match(raw)
        m_string = RE_STRINGDATA_BLOCK.match(raw)
        if m_data or m_string:
            base_indent = len((m_data or m_string).group(1))
            j = i + 1
            while j < n:
                nxt = lines[j]
                if nxt.strip() == "":
                    j += 1
                    continue
                cur_indent = len(nxt) - len(nxt.lstrip(" "))
                if cur_indent <= base_indent and nxt.strip():
                    break
                if RE_SUPPRESS.search(nxt):
                    j += 1
                    continue
                if m_data:
                    sm = RE_DATA_SCALAR.match(nxt)
                    if sm:
                        key = sm.group(2)
                        value = sm.group(4) if sm.group(4) is not None else (sm.group(5) or "")
                        value = value.strip()
                        line_no = doc_start + j
                        if not value:
                            j += 1
                            continue
                        ok, decoded = try_b64_decode(value)
                        if not ok:
                            # Could be plaintext mistakenly placed in
                            # data: — flag if non-placeholder.
                            if not looks_placeholder(value):
                                findings.append(
                                    (path, line_no, 1,
                                     "k8s-secret-data-undecodable-non-placeholder",
                                     f"data.{key}: not valid base64")
                                )
                            j += 1
                            continue
                        if looks_placeholder(decoded):
                            j += 1
                            continue
                        why = matches_known_credential(decoded)
                        if why is None and looks_high_entropy_password(decoded):
                            why = "high-entropy"
                        if why:
                            findings.append(
                                (path, line_no, 1,
                                 "k8s-secret-data-with-base64-secret",
                                 f"data.{key}: decodes to real-looking secret ({why})")
                            )
                else:
                    sm = RE_STRINGDATA_SCALAR.match(nxt)
                    if sm:
                        key = sm.group(2)
                        value = sm.group(4) if sm.group(4) is not None else (sm.group(5) or "")
                        value = value.strip()
                        line_no = doc_start + j
                        if not value:
                            j += 1
                            continue
                        if looks_placeholder(value):
                            j += 1
                            continue
                        why = matches_known_credential(value)
                        if why is None and looks_high_entropy_password(value):
                            why = "high-entropy"
                        if why:
                            findings.append(
                                (path, line_no, 1,
                                 "k8s-secret-stringdata-with-secret",
                                 f"stringData.{key}: real-looking secret ({why})")
                            )
                j += 1
            i = j
        else:
            i += 1
    return findings


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings = []
    for doc_start, doc_text in split_docs(text):
        if not is_secret_doc(doc_text):
            continue
        # Skip CRDs that aren't core/v1 Secret (heuristic: kind says
        # SealedSecret etc). RE_KIND_SECRET is exact word "Secret".
        # SealedSecret would not match because the regex anchors the
        # whole value.
        findings.extend(scan_secret_doc(path, doc_start, doc_text))
    return findings


def iter_targets(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and sub.suffix.lower() in SUFFIXES:
                    yield sub
        elif p.is_file():
            yield p


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <file_or_dir> [...]", file=sys.stderr)
        return 2
    total = 0
    for path in iter_targets(argv[1:]):
        for f_path, line, col, kind, snippet in scan_file(path):
            print(f"{f_path}:{line}:{col}: {kind} \u2014 {snippet}")
            total += 1
    print(f"# {total} finding(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
