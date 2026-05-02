#!/usr/bin/env python3
"""Detect Apache Tomcat ``tomcat-users.xml`` (or equivalent inline
config) that ships the Manager / Host-Manager web apps with default,
weak, or trivially-guessable credentials.

Background
==========

Tomcat's ``manager-gui``, ``manager-script``, ``manager-jmx``, and
``manager-status`` roles unlock /manager/html, /manager/text,
/manager/jmxproxy, etc. Anyone holding a role with one of these
permissions can deploy a WAR (i.e., remote code execution).

Upstream's stock ``conf/tomcat-users.xml`` ships **commented out**
precisely so that no manager account exists at install time. LLMs
generating onboarding scripts very frequently re-introduce the
example block verbatim — usernames like ``tomcat``, ``admin``,
``manager``, ``role1`` paired with passwords ``tomcat``, ``s3cret``,
``password``, ``admin``, ``changeit``, an empty string, or the
username repeated. Any such pairing on a manager-* role is a
straight RCE waiting to be scanned for on port 8080.

What this detector flags
========================

For every active (non-comment) ``<user .../>`` element it parses,
emit a finding when both:

  * any ``roles=`` attribute contains a token that begins with
    ``manager`` or ``admin`` (e.g. ``manager-gui``, ``manager-script``,
    ``admin-gui``); **and**
  * the ``password=`` attribute is in the well-known weak set, is
    empty, or equals the ``username=`` value.

A file containing the comment marker
``tomcat-manager-default-creds-allowed`` is treated as suppressed
(useful for CTF / honeypot fixtures).

Usage
=====

    python3 detector.py path/to/tomcat-users.xml [more files...]

Exit code equals the number of findings; ``0`` means clean.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS_MARK = "tomcat-manager-default-creds-allowed"

WEAK_PASSWORDS = {
    "",
    "tomcat",
    "admin",
    "manager",
    "password",
    "passw0rd",
    "s3cret",
    "secret",
    "changeit",
    "changeme",
    "12345",
    "123456",
    "root",
    "letmein",
    "welcome",
    "default",
}

PRIVILEGED_ROLE_PREFIXES = ("manager", "admin")

# Strip XML/HTML comments so we don't flag the upstream commented-out example.
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
USER_TAG_RE = re.compile(r"<user\b([^/>]*)/?>", re.IGNORECASE)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*"([^"]*)\"""")


def parse_user_attrs(tag_inner: str) -> dict[str, str]:
    return {k.lower(): v for k, v in ATTR_RE.findall(tag_inner)}


def has_privileged_role(roles_attr: str) -> bool:
    for tok in (t.strip() for t in roles_attr.split(",")):
        low = tok.lower()
        for prefix in PRIVILEGED_ROLE_PREFIXES:
            if low == prefix or low.startswith(prefix + "-"):
                return True
    return False


def scan(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"{path}: cannot read ({exc})"]

    if SUPPRESS_MARK in text:
        return []

    stripped = COMMENT_RE.sub("", text)
    findings: list[str] = []

    for match in USER_TAG_RE.finditer(stripped):
        attrs = parse_user_attrs(match.group(1))
        username = attrs.get("username", "")
        password = attrs.get("password", "")
        roles = attrs.get("roles", "")
        if not has_privileged_role(roles):
            continue
        weak_reason = None
        if password.lower() in WEAK_PASSWORDS:
            weak_reason = f"weak password {password!r}"
        elif password == username and username:
            weak_reason = "password equals username"
        if weak_reason is not None:
            findings.append(
                f"{path}: privileged user {username!r} on roles "
                f"{roles!r} uses {weak_reason}"
            )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detector.py <file> [<file>...]",
            file=sys.stderr,
        )
        return 0
    findings: list[str] = []
    for arg in argv[1:]:
        findings.extend(scan(Path(arg)))
    for f in findings:
        print(f)
    return len(findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
