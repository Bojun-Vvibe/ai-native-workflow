#!/usr/bin/env python3
"""Detect Matrix Synapse homeserver configurations from LLM output
where ``enable_registration: true`` is set without any of the
abuse-mitigation knobs that upstream requires.

Synapse (https://element-hq.github.io/synapse/latest/) refuses by
default to start with open registration unless one of the
following is present:

  - ``enable_registration_captcha: true`` (with reCAPTCHA keys), or
  - ``registrations_require_3pid:`` with at least one entry, or
  - ``registration_requires_token: true`` (token-gated), or
  - ``enable_registration_without_verification: true`` (the
    operator explicitly opting in to a fully open server).

LLM-generated ``homeserver.yaml`` snippets routinely flip
``enable_registration: true`` to "make signup work" while dropping
every guard, and then add
``enable_registration_without_verification: true`` to silence the
startup error. The result is a homeserver that any spammer can
fill with throwaway accounts, federate from, and use for relay
abuse.

This detector flags four orthogonal regressions on configs that
are clearly Synapse (mention ``server_name:``, the ``synapse``
docker image, ``homeserver.yaml``, or ``matrix-synapse``):

  1. ``enable_registration: true`` AND none of the four guard keys
     above is set.
  2. ``enable_registration: true`` AND
     ``enable_registration_without_verification: true`` (operator
     bypass of the upstream safety check, with no compensating
     token / 3pid / captcha).
  3. ``registration_shared_secret:`` is set to an obvious default
     / placeholder value (``"changeme"``, ``"CHANGEME"``,
     ``"secret"``, ``"REPLACE_ME"``, ``"<random>"``, empty string).
  4. ``enable_registration_captcha: true`` is set but
     ``recaptcha_public_key`` / ``recaptcha_private_key`` is
     missing or left as a placeholder — the captcha gate is
     non-functional and Synapse will fall back to open
     registration in some misconfigurations.

Suppression: a top-level ``# synapse-registration-ok`` comment in
the file disables all rules (use only when the homeserver is
firewalled to a private network).

CWE refs: CWE-1188 (Insecure Default Initialization of Resource),
CWE-307 (Improper Restriction of Excessive Authentication
Attempts), CWE-693 (Protection Mechanism Failure).

Public API:
    scan(text: str) -> list[tuple[int, str]]
        Returns a list of (line_number_1based, reason) tuples.
        Empty list = clean.

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

SUPPRESS = re.compile(r"#\s*synapse-registration-ok", re.IGNORECASE)

SYNAPSE_MARKERS = [
    re.compile(r"(?im)^\s*server_name\s*:\s*[\"']?[a-z0-9.\-]+\.[a-z]{2,}"),
    re.compile(r"(?im)^\s*image\s*:\s*[\"']?(?:matrixdotorg|element-hq|ghcr\.io/element-hq)/synapse"),
    re.compile(r"\bhomeserver\.yaml\b", re.IGNORECASE),
    re.compile(r"\bmatrix-synapse\b", re.IGNORECASE),
    re.compile(r"(?im)^\s*pid_file\s*:\s*[\"']?/data/homeserver\.pid"),
]

ENABLE_REGISTRATION_TRUE = re.compile(
    r"(?im)^(?P<indent>\s*)enable_registration\s*:\s*(?:true|yes|on)\s*(?:#.*)?$"
)
ENABLE_REGISTRATION_FALSE = re.compile(
    r"(?im)^\s*enable_registration\s*:\s*(?:false|no|off)\s*(?:#.*)?$"
)
ENABLE_REG_NO_VERIFICATION_TRUE = re.compile(
    r"(?im)^\s*enable_registration_without_verification\s*:\s*(?:true|yes|on)\s*(?:#.*)?$"
)
ENABLE_REG_CAPTCHA_TRUE = re.compile(
    r"(?im)^\s*enable_registration_captcha\s*:\s*(?:true|yes|on)\s*(?:#.*)?$"
)
REGISTRATION_REQUIRES_TOKEN_TRUE = re.compile(
    r"(?im)^\s*registration_requires_token\s*:\s*(?:true|yes|on)\s*(?:#.*)?$"
)
REGISTRATIONS_REQUIRE_3PID_BLOCK = re.compile(
    r"(?im)^\s*registrations_require_3pid\s*:\s*(?:\n\s*-\s*\S+|\[[^\]]*\S[^\]]*\])"
)

REG_SHARED_SECRET = re.compile(
    r"(?im)^\s*registration_shared_secret\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S+)\s*(?:#.*)?$"
)

RECAPTCHA_PUBLIC = re.compile(
    r"(?im)^\s*recaptcha_public_key\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S+)?\s*(?:#.*)?$"
)
RECAPTCHA_PRIVATE = re.compile(
    r"(?im)^\s*recaptcha_private_key\s*:\s*(?P<val>\"[^\"]*\"|'[^']*'|\S+)?\s*(?:#.*)?$"
)

PLACEHOLDER_VALUES = {
    "", "changeme", "change-me", "change_me", "secret", "password",
    "replace_me", "replaceme", "replace-me", "<random>", "<changeme>",
    "todo", "xxx", "xxxx", "your_secret_here", "your-secret-here",
    "yoursecrethere", "default", "example",
}


def _strip(v: str) -> str:
    return v.strip().strip("'\"")


def _is_synapse_config(text: str) -> bool:
    return any(m.search(text) for m in SYNAPSE_MARKERS)


def _line_of(text: str, needle_re: re.Pattern) -> int:
    for i, ln in enumerate(text.splitlines(), start=1):
        if needle_re.search(ln):
            return i
    return 1


def scan(text: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(text):
        return []
    if not _is_synapse_config(text):
        return []

    findings: List[Tuple[int, str]] = []

    enable_match = ENABLE_REGISTRATION_TRUE.search(text)
    # If both true and false appear (e.g. commented examples), the
    # explicit false earlier in the file does NOT cancel a later
    # true. Just check for the presence of an active true line.
    if not enable_match:
        # If nothing is enabling registration, the config is fine
        # for the purposes of these rules.
        # Still check shared-secret placeholder rule below.
        enable_active = False
    else:
        enable_active = True

    captcha_active = bool(ENABLE_REG_CAPTCHA_TRUE.search(text))
    token_active = bool(REGISTRATION_REQUIRES_TOKEN_TRUE.search(text))
    threepid_active = bool(REGISTRATIONS_REQUIRE_3PID_BLOCK.search(text))
    no_verify_active = bool(ENABLE_REG_NO_VERIFICATION_TRUE.search(text))

    has_any_guard = captcha_active or token_active or threepid_active

    if enable_active and not has_any_guard and not no_verify_active:
        line = enable_match.start()
        line_no = text.count("\n", 0, line) + 1
        findings.append(
            (
                line_no,
                "enable_registration: true with no captcha / token / 3pid guard "
                "(set enable_registration_captcha, registration_requires_token, "
                "or registrations_require_3pid)",
            )
        )

    if enable_active and no_verify_active and not has_any_guard:
        line_no = _line_of(text, ENABLE_REG_NO_VERIFICATION_TRUE)
        findings.append(
            (
                line_no,
                "enable_registration_without_verification: true bypasses the "
                "upstream safety check; the homeserver will accept anonymous "
                "signups with no captcha / token / 3pid",
            )
        )

    if captcha_active:
        pub = RECAPTCHA_PUBLIC.search(text)
        priv = RECAPTCHA_PRIVATE.search(text)
        pub_val = _strip(pub.group("val") or "") if (pub and pub.group("val")) else ""
        priv_val = _strip(priv.group("val") or "") if (priv and priv.group("val")) else ""
        if (
            (pub is None or pub_val.lower() in PLACEHOLDER_VALUES)
            or (priv is None or priv_val.lower() in PLACEHOLDER_VALUES)
        ):
            line_no = _line_of(text, ENABLE_REG_CAPTCHA_TRUE)
            findings.append(
                (
                    line_no,
                    "enable_registration_captcha: true but recaptcha_public_key / "
                    "recaptcha_private_key is missing or left as a placeholder "
                    "(captcha gate is non-functional)",
                )
            )

    secret = REG_SHARED_SECRET.search(text)
    if secret is not None:
        sval = _strip(secret.group("val"))
        if sval.lower() in PLACEHOLDER_VALUES:
            line_no = text.count("\n", 0, secret.start()) + 1
            findings.append(
                (
                    line_no,
                    "registration_shared_secret is set to a placeholder value "
                    "(" + (sval or "<empty>") + "); anyone who reads the file "
                    "can register privileged accounts via the admin API",
                )
            )

    return findings


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
