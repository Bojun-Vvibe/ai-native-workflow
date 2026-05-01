#!/usr/bin/env python3
"""Detect hardcoded Azure Storage connection strings / SAS tokens / account keys.

Azure Storage credentials follow well-known shapes that LLMs love
to splat into source files when generating "quick start" snippets:

* Connection strings of the form
  `DefaultEndpointsProtocol=...;AccountName=...;AccountKey=...;...`
  with a literal `AccountKey=<base64>` segment.
* `SharedAccessSignature=sv=...&sig=...` segments inside a
  connection-string-shaped literal.
* Bare `AccountKey=<base64>` assignments inside a literal.
* Standalone SAS query strings: a URL or string literal containing
  `?sv=YYYY-MM-DD&...&sig=<urlencoded-base64>` segments.
* Account-key-looking 88-char base64 string literals assigned to a
  variable named `accountKey`, `account_key`, `AZURE_STORAGE_KEY`,
  `STORAGE_KEY`, or `AccountKey`.

What this flags
---------------
* `azure-storage-connection-string-with-account-key` — connection
  string literal containing `AccountKey=<base64-ish>` (>= 40 chars,
  not the literal placeholder `<your-key>` / `your_key_here` /
  `${...}` / `%...%` / `{{...}}`).
* `azure-storage-connection-string-with-sas` — connection string
  literal containing `SharedAccessSignature=sv=...&sig=...`.
* `azure-storage-bare-account-key-assignment` — variable named
  `(account|storage)_?key` (case-insensitive) assigned a quoted
  ~88-char base64-looking string literal.
* `azure-storage-sas-token-in-url` — string containing
  `?sv=YYYY-MM-DD&...&sig=<base64-ish>` (a service SAS or account
  SAS), where `<base64-ish>` is at least 20 chars of urlencoded
  base64.

What this does NOT flag
-----------------------
* Connection strings whose `AccountKey=` value is obviously a
  placeholder (`<...>`, `${...}`, `%...%`, `{{...}}`, contains
  the literal `your`, `placeholder`, `example`, `redacted`,
  `xxx`, `fake`, or is shorter than 40 chars).
* Lines marked with a trailing `# az-storage-key-ok` comment
  (or `// az-storage-key-ok` for C-family).
* Patterns inside `#` or `//` comment-only lines.
* Use of `DefaultAzureCredential` / `ManagedIdentityCredential` /
  `AZURE_STORAGE_ACCOUNT` env reads with no key in source.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories. Looks at common config / source extensions:
.py .js .mjs .cjs .ts .tsx .jsx .cs .go .rb .java .kt .scala .php
.rs .swift .m .mm .json .jsonc .yml .yaml .toml .ini .conf .cfg
.env .properties .sh .bash .ps1 .bicep .tf .hcl .xml .config .md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".cs",
    ".go", ".rb", ".java", ".kt", ".scala", ".php", ".rs",
    ".swift", ".m", ".mm", ".json", ".jsonc", ".yml", ".yaml",
    ".toml", ".ini", ".conf", ".cfg", ".env", ".properties",
    ".sh", ".bash", ".ps1", ".bicep", ".tf", ".hcl", ".xml",
    ".config", ".md",
}


RE_SUPPRESS = re.compile(r"(?:#|//)\s*az-storage-key-ok\b")
RE_COMMENT_ONLY = re.compile(r"^\s*(?:#|//)")

# Connection string shape: must contain DefaultEndpointsProtocol or
# AccountName, plus an AccountKey= or SharedAccessSignature= part.
RE_CONN_ACCOUNTKEY = re.compile(
    r"(?:DefaultEndpointsProtocol\s*=|AccountName\s*=|BlobEndpoint\s*=)[^\"'\n]{1,400}?"
    r"AccountKey\s*=\s*([A-Za-z0-9+/=]{20,})",
)
RE_CONN_SAS = re.compile(
    r"(?:DefaultEndpointsProtocol\s*=|AccountName\s*=|BlobEndpoint\s*=|QueueEndpoint\s*=|TableEndpoint\s*=|FileEndpoint\s*=)[^\"'\n]{1,400}?"
    r"SharedAccessSignature\s*=\s*sv=\d{4}-\d{2}-\d{2}[^\"'\s]*?&sig=[A-Za-z0-9%+/=]{20,}",
)

# Bare AccountKey assignment via (account|storage)_?key = "<88-ish base64>"
RE_BARE_KEY = re.compile(
    r"""(?ix)
    \b(?:account|storage)[ _-]?key\b
    ['"]?\s*[:=]\s*
    (['"])([A-Za-z0-9+/]{40,}={0,2})\1
    """,
)

# AZURE_STORAGE_KEY=... in dotenv style
RE_DOTENV_KEY = re.compile(
    r"""(?ix)
    ^\s*
    (?:AZURE_STORAGE_KEY|AZURE_STORAGE_ACCOUNT_KEY|STORAGE_ACCOUNT_KEY)
    \s*=\s*
    ['"]?([A-Za-z0-9+/]{40,}={0,2})['"]?\s*$
    """,
)

# SAS query string in a URL: ?sv=YYYY-MM-DD&...&sig=<base64>
RE_SAS_URL = re.compile(
    r"""\?sv=\d{4}-\d{2}-\d{2}[^"'\s]{0,400}?&sig=([A-Za-z0-9%+/=]{20,})""",
)


PLACEHOLDER_WORDS = (
    "your", "placeholder", "example", "redacted",
    "fake_replace", "dummy", "changeme", "todo_replace",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"<[^>]+>"),
    re.compile(r"\$\{[^}]+\}"),
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"%[A-Z_][A-Z0-9_]*%"),
    re.compile(r"x{6,}", re.IGNORECASE),
)


def looks_like_placeholder(value: str) -> bool:
    v = value.lower()
    for tok in PLACEHOLDER_WORDS:
        if tok in v:
            return True
    for pat in PLACEHOLDER_PATTERNS:
        if pat.search(value):
            return True
    # Single character repeated 90%+ of the string (e.g. "AAAA...").
    if len(value) >= 20:
        most = max(value.count(c) for c in set(value))
        if most / len(value) >= 0.9:
            return True
    return False


def scan_text(path: Path, text: str):
    findings = []
    lines = text.splitlines()

    for idx, raw in enumerate(lines, start=1):
        if RE_SUPPRESS.search(raw):
            continue
        if RE_COMMENT_ONLY.match(raw):
            continue

        m = RE_CONN_ACCOUNTKEY.search(raw)
        if m and not looks_like_placeholder(m.group(1)):
            findings.append(
                (path, idx, m.start() + 1,
                 "azure-storage-connection-string-with-account-key",
                 raw.strip()[:200])
            )
            # Don't double-flag the same line on bare-key.
            continue

        m = RE_CONN_SAS.search(raw)
        if m:
            findings.append(
                (path, idx, m.start() + 1,
                 "azure-storage-connection-string-with-sas",
                 raw.strip()[:200])
            )
            continue

        m = RE_BARE_KEY.search(raw)
        if m and not looks_like_placeholder(m.group(2)):
            findings.append(
                (path, idx, m.start() + 1,
                 "azure-storage-bare-account-key-assignment",
                 raw.strip()[:200])
            )
            continue

        m = RE_DOTENV_KEY.search(raw)
        if m and not looks_like_placeholder(m.group(1)):
            findings.append(
                (path, idx, 1,
                 "azure-storage-bare-account-key-assignment",
                 raw.strip()[:200])
            )
            continue

        m = RE_SAS_URL.search(raw)
        if m and not looks_like_placeholder(m.group(1)):
            findings.append(
                (path, idx, m.start() + 1,
                 "azure-storage-sas-token-in-url",
                 raw.strip()[:200])
            )
            continue

    return findings


def iter_targets(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if not sub.is_file():
                    continue
                name = sub.name.lower()
                if (sub.suffix.lower() in SUFFIXES
                        or name == ".env"
                        or name.endswith(".env")
                        or name.endswith(".dotenv")
                        or ".env." in name):
                    yield sub
        elif p.is_file():
            yield p


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(path, text)


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
