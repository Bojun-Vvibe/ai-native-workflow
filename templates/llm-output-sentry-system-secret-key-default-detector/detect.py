#!/usr/bin/env python3
"""
llm-output-sentry-system-secret-key-default-detector

Flags self-hosted Sentry deployments whose ``system.secret-key`` is
left at the documented placeholder value -- typically the literal
``!!changeme!!`` sentinel that ships in the upstream
``sentry/sentry`` ``sentry.conf.py`` template, or another
well-known no-op string (``changeme``, ``CHANGEME``,
``secret``, ``please-change-me``).

Upstream:
  - getsentry/self-hosted: https://github.com/getsentry/self-hosted
  - getsentry/sentry: https://github.com/getsentry/sentry
  - sentry config doc:
    https://develop.sentry.dev/self-hosted/#sentry-secret-key
  - Tested against self-hosted versions 23.x .. 24.x where the
    template sentinel ``!!changeme!!`` is still emitted by
    ``install.sh``.

Concrete forms detected (each requires Sentry context in-file):

1. ``sentry.conf.py`` / ``config.yml`` containing
   ``system.secret-key: '!!changeme!!'`` (or any of the well-known
   placeholder strings).
2. ``SECRET_KEY = '!!changeme!!'`` Python assignment in a Sentry
   settings file.
3. Docker / k8s env var ``SENTRY_SECRET_KEY=!!changeme!!`` (or
   ``=changeme`` / ``=secret`` / ``=please-change-me``).
4. ``sentry config generate-secret-key`` documented but the
   resulting ``system.secret-key`` still set to the placeholder
   in the same file.

Why this is dangerous
---------------------
Sentry's ``system.secret-key`` is the cryptographic root of the
self-hosted install. It signs and validates:

- session cookies (Django ``SECRET_KEY`` semantics) -> session
  forgery / privilege escalation to a Sentry superuser;
- HMAC tokens used for "magic link" email auth and password
  reset -> attacker-issued reset tokens;
- relay-to-sentry signed requests when an external Relay is
  configured -> arbitrary event ingestion / spoofing of any
  project's events;
- the ``_csrf`` token derivation -> bypass of CSRF on the
  ``/api/0/`` admin surface.

Anyone who knows the value can mint a valid superuser session
without ever touching the database. The ``!!changeme!!`` literal
is shipped in the upstream template and is therefore world-
known.

Maps to:
  - CWE-798: Use of Hard-coded Credentials
  - CWE-1392: Use of Default Credentials
  - CWE-321: Use of Hard-coded Cryptographic Key
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A02:2021 Cryptographic Failures
  - OWASP A07:2021 Identification and Authentication Failures

Heuristic
---------
We require Sentry context (any of: ``sentry``, ``getsentry``,
``snuba``, ``sentry.conf.py``, ``SENTRY_``) to avoid flagging
unrelated Django ``SECRET_KEY`` settings.

Stdlib-only.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

_SENTRY_CONTEXT = re.compile(
    r"""(?im)\b(?:sentry|getsentry|snuba|SENTRY_[A-Z_]+|sentry\.conf\.py)\b""",
)

# Known placeholder values, anchored on quoted/unquoted strings.
_PLACEHOLDER = (
    r"""(?:!!changeme!!|changeme|CHANGEME|"""
    r"""please[-_]change[-_]me|please_change_this|"""
    r"""replace[-_]me|secret|"""
    r"""your[-_]secret[-_]key[-_]here|"""
    r"""generated[-_]secret[-_]key|"""
    r"""<your-secret-key>)"""
)

# YAML/INI form: system.secret-key: '!!changeme!!'
_YAML_SECRET = re.compile(
    r"""(?im)^\s*system\.secret-key\s*:\s*['"]?(""" + _PLACEHOLDER + r""")['"]?\s*(?:#.*)?$""",
)

# Python form: SECRET_KEY = '!!changeme!!'   (only flagged if file
# carries Sentry context -- handled by the gate)
_PY_SECRET = re.compile(
    r"""(?im)^\s*SECRET_KEY\s*=\s*['"](""" + _PLACEHOLDER + r""")['"]""",
)

# Env / docker-compose: SENTRY_SECRET_KEY=!!changeme!!   or
#                       SENTRY_SECRET_KEY: '!!changeme!!'
_ENV_SECRET = re.compile(
    r"""(?im)\bSENTRY_SECRET_KEY\s*[:=]\s*['"]?(""" + _PLACEHOLDER + r""")['"]?\s*$""",
)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return ""


def scan(path: str) -> List[str]:
    text = _read(path)
    if not text:
        return []
    if not _SENTRY_CONTEXT.search(text):
        return []

    findings: List[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue

        for rx, label in (
            (_YAML_SECRET, "system.secret-key"),
            (_PY_SECRET, "SECRET_KEY"),
            (_ENV_SECRET, "SENTRY_SECRET_KEY"),
        ):
            m = rx.search(raw)
            if m:
                findings.append(
                    f"{path}:{i}: sentry {label} left at the "
                    f"documented placeholder value '{m.group(1)}' "
                    f"-> the cryptographic root of the install is "
                    f"world-known: any reader of the upstream "
                    f"sentry.conf.py template can mint a valid "
                    f"superuser session, forge magic-link / "
                    f"password-reset HMAC tokens, and spoof Relay "
                    f"event ingestion (CWE-798/CWE-1392/CWE-321/"
                    f"CWE-1188): {raw.strip()[:200]}"
                )
                break
    return findings


_TARGET_EXTS = (".conf", ".cfg", ".properties",
                ".yaml", ".yml", ".json", ".sh", ".bash",
                ".service", ".dockerfile", ".ini", ".toml",
                ".py", ".env")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low.startswith("dockerfile") or \
                            low.startswith("docker-compose") or \
                            low.endswith(_TARGET_EXTS):
                        yield os.path.join(dp, f)
        else:
            yield r


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: detect.py <file-or-dir> [more...]\n")
        return 2
    any_finding = False
    for path in iter_paths(argv[1:]):
        for line in scan(path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
