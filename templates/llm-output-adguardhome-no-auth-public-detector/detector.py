#!/usr/bin/env python3
"""Detect AdGuard Home (``AdGuardHome.yaml``) deployments that expose
the admin web UI / DNS API without authentication, or with a default
/ trivially-weak admin credential, while binding to a non-loopback
address.

AdGuard Home (https://adguard.com/en/adguard-home/overview.html) is
a self-hosted DNS-over-HTTPS / DNS-over-TLS resolver and ad-blocker.
The admin UI lets the operator add upstreams, rewrite rules,
allowlists / blocklists, and configure DHCP — i.e. it can silently
hijack every DNS lookup of every device that uses it. The shipped
``AdGuardHome.yaml`` controls auth via:

  users:
    - name: admin
      password: <bcrypt hash>

If the ``users`` list is empty or absent **and** the ``http`` /
``bind_host`` is something other than localhost, AdGuardHome will
serve the admin UI to any client that can reach the port (default
``3000`` for setup, ``80``/``443`` after install). LLMs frequently
emit such configs because the post-install YAML literally has an
empty ``users: []`` block until the first-run wizard runs, and
copy-paste examples skip the wizard step.

This detector flags four orthogonal regressions:

  1. ``users:`` missing / empty (``[]`` or no items) **and**
     ``bind_host``/``http.address`` resolves to a non-loopback host.
  2. ``users:`` present, but the ``password`` field is empty,
     literally ``"<bcrypt-hash>"`` placeholder, or not a bcrypt
     hash (bcrypt hashes start with ``$2a$``, ``$2b$``, or ``$2y$``)
     — meaning the YAML stores a plaintext password.
  3. ``users:`` contains a name in the curated weak set (``admin``,
     ``root``, ``test``, ``user``) paired with a password whose
     bcrypt cost (``$2b$<NN>$``) is below 10.
  4. ``auth_attempts: 0`` or ``block_auth_min: 0`` — disables the
     built-in brute-force lock-out and is documented as a foot-gun.

Suppression: a top-of-file comment
``# adguardhome-no-auth-public-allowed`` silences all rules.

CWE refs:
  * CWE-306: Missing Authentication for Critical Function
  * CWE-521: Weak Password Requirements
  * CWE-1188: Insecure Default Initialization of Resource

Public API:
    scan(text: str) -> list[tuple[int, str]]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding (capped 255).
    Stdout: ``<file>:<line>:<reason>``.

Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

SUPPRESS = re.compile(r"#\s*adguardhome-no-auth-public-allowed", re.IGNORECASE)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "[::1]"}

WEAK_USERNAMES = {"admin", "administrator", "root", "test", "user", "adguard"}

PLACEHOLDER_PASS = {
    "",
    "<bcrypt-hash>",
    "<bcrypt>",
    "<password>",
    "<changeme>",
    "<change-me>",
    "<placeholder>",
    "<todo>",
    "todo",
    "changeme",
    "change-me",
    "password",
    "admin",
    "secret",
}

BCRYPT_RE = re.compile(r"^\$2[aby]\$(\d{2})\$")


def _strip_yaml_comment(line: str) -> str:
    out: List[str] = []
    in_s = False
    in_d = False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(val: str) -> str:
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (
        v.startswith("'") and v.endswith("'")
    ):
        return v[1:-1]
    return v


def _is_loopback(host: str) -> bool:
    h = host.strip().strip("'").strip('"')
    if not h:
        return False
    # strip [::1]:port style
    h = h.strip("[]")
    h = h.split("/", 1)[0]
    if ":" in h and not h.startswith("::"):
        h = h.rsplit(":", 1)[0]
    return h.lower() in LOCAL_HOSTS


def _looks_relevant(source: str) -> bool:
    # AdGuard Home YAMLs always have these top-level keys.
    has_dns = re.search(r"(?m)^dns\s*:\s*$", source) is not None
    has_users = re.search(r"(?m)^users\s*:", source) is not None
    has_bind = re.search(r"(?m)^\s*bind_host\s*:", source) is not None
    has_http = re.search(r"(?m)^\s*http\s*:\s*$", source) is not None
    return (has_users and (has_bind or has_http)) or (has_dns and has_users)


def _find_top_block_end(lines: List[str], start: int) -> int:
    """Given the line index of a top-level ``key:`` mapping, return
    the index of the last line belonging to that block (inclusive).
    """
    base = _indent(lines[start])
    end = start
    j = start + 1
    while j < len(lines):
        rj = lines[j]
        if not rj.strip():
            j += 1
            continue
        ij = _indent(rj)
        if ij <= base:
            break
        end = j
        j += 1
    return end


def _scan_users(lines: List[str]) -> Tuple[bool, List[Tuple[int, str]], int]:
    """Return (has_user_with_password, findings, users_line_no_1based).
    users_line_no_1based is 0 if no ``users:`` key exists.
    """
    findings: List[Tuple[int, str]] = []
    users_line = 0
    has_user_with_pw = False

    for i, raw in enumerate(lines):
        s = _strip_yaml_comment(raw)
        m = re.match(r"^users\s*:\s*(.*)$", s)
        if not m or _indent(raw) != 0:
            continue
        users_line = i + 1
        rhs = m.group(1).strip()
        # users: []
        if rhs in ("[]", "~", "null"):
            return has_user_with_pw, findings, users_line
        if rhs and rhs != "":
            # Inline non-list value, not what we expect.
            return has_user_with_pw, findings, users_line
        # Block-style list.
        end = _find_top_block_end(lines, i)
        # Walk children, group by `- name:` markers.
        cur_name: Optional[Tuple[int, str]] = None
        cur_pw: Optional[Tuple[int, str]] = None

        def _flush(cn, cp):
            nonlocal has_user_with_pw
            if cn is None:
                return
            name_ln, name_val = cn
            if cp is None:
                findings.append(
                    (name_ln, f"users[].name={name_val!r} declared without a password")
                )
                return
            pw_ln, pw_val = cp
            has_user_with_pw = True
            low = pw_val.strip().lower()
            if low in PLACEHOLDER_PASS:
                findings.append(
                    (pw_ln, f"users[].password={pw_val!r} is empty / placeholder")
                )
                return
            bm = BCRYPT_RE.match(pw_val.strip())
            if not bm:
                findings.append(
                    (pw_ln, f"users[].password is not a bcrypt hash (must start with $2a$/$2b$/$2y$)")
                )
                return
            cost = int(bm.group(1))
            if cost < 10 and name_val.lower() in WEAK_USERNAMES:
                findings.append(
                    (pw_ln, f"users[].name={name_val!r} paired with bcrypt cost {cost} < 10")
                )

        for j in range(i + 1, end + 1):
            rj = lines[j]
            sj = _strip_yaml_comment(rj)
            if not sj.strip():
                continue
            mn = re.match(r"^\s*-\s*name\s*:\s*(.*)$", sj)
            if mn:
                _flush(cur_name, cur_pw)
                cur_name = (j + 1, _unquote(mn.group(1)))
                cur_pw = None
                continue
            mp = re.match(r"^\s*password\s*:\s*(.*)$", sj)
            if mp:
                cur_pw = (j + 1, _unquote(mp.group(1)))
                continue
            mn2 = re.match(r"^\s*name\s*:\s*(.*)$", sj)
            if mn2 and cur_name is not None and cur_name[0] != j + 1:
                # Another field — ignore.
                pass
        _flush(cur_name, cur_pw)
        return has_user_with_pw, findings, users_line

    return has_user_with_pw, findings, users_line


def _find_bind(lines: List[str]) -> Optional[Tuple[int, str]]:
    """Return (line_no_1based, host) for the admin-UI bind address.
    Looks at top-level ``bind_host`` and at ``http.address`` /
    ``http.bind_hosts``.
    """
    # top-level bind_host
    for i, raw in enumerate(lines):
        s = _strip_yaml_comment(raw)
        m = re.match(r"^bind_host\s*:\s*(.*)$", s)
        if m and _indent(raw) == 0:
            return (i + 1, _unquote(m.group(1)))
    # http: \n  address: x:port  OR  bind_hosts: [ ... ]
    for i, raw in enumerate(lines):
        s = _strip_yaml_comment(raw).rstrip()
        if re.match(r"^http\s*:\s*$", s) and _indent(raw) == 0:
            end = _find_top_block_end(lines, i)
            for j in range(i + 1, end + 1):
                rj = lines[j]
                sj = _strip_yaml_comment(rj)
                ma = re.match(r"^\s*address\s*:\s*(.*)$", sj)
                if ma:
                    return (j + 1, _unquote(ma.group(1)))
                mb = re.match(r"^\s*bind_hosts\s*:\s*\[\s*(.*?)\s*\]\s*$", sj)
                if mb:
                    items = [_unquote(x.strip()) for x in mb.group(1).split(",") if x.strip()]
                    for item in items:
                        if not _is_loopback(item):
                            return (j + 1, item)
                    if items:
                        return (j + 1, items[0])
    return None


def _find_attempt_knobs(lines: List[str]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        s = _strip_yaml_comment(raw)
        for key in ("auth_attempts", "block_auth_min"):
            m = re.match(rf"^\s*{key}\s*:\s*(\S+)\s*$", s)
            if m:
                try:
                    val = int(m.group(1))
                except ValueError:
                    continue
                if val == 0:
                    out.append((i, f"{key}={val} disables brute-force lock-out"))
    return out


def scan(source: str) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    if not _looks_relevant(source):
        return []
    lines = source.splitlines()
    findings: List[Tuple[int, str]] = []

    has_pw_user, user_findings, users_ln = _scan_users(lines)
    findings.extend(user_findings)

    bind = _find_bind(lines)
    bind_remote = bind is not None and not _is_loopback(bind[1])

    if not has_pw_user and not user_findings:
        # users: missing entirely OR users: [] OR users: with no name entries.
        if bind_remote:
            ln = users_ln if users_ln else (bind[0] if bind else 1)
            findings.append(
                (ln, f"users list is empty/absent and admin UI bound to non-loopback host {bind[1]!r}")
            )

    findings.extend(_find_attempt_knobs(lines))

    return sorted({(l, r) for l, r in findings})


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in ("*.yaml", "*.yml"):
                targets.extend(sorted(path.rglob(pat)))
        else:
            targets.append(path)
    seen = set()
    for f in targets:
        if f in seen:
            continue
        seen.add(f)
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan(source)
        if hits:
            bad_files += 1
            for line, reason in hits:
                print(f"{f}:{line}:{reason}")
    return bad_files


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 0
    paths = [Path(a) for a in argv[1:]]
    return min(255, scan_paths(paths))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
