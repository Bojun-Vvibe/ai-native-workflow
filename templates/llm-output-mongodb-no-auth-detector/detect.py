#!/usr/bin/env python3
"""Detect MongoDB configurations that disable authentication.

A `mongod` process started without authentication accepts every
client on every reachable interface as a fully-privileged user.
The historical default was "auth off + bind 127.0.0.1", and the
docker-compose / kubernetes / helm shapes LLMs emit routinely flip
the bind to `0.0.0.0` while leaving auth off, producing the
canonical "publicly reachable, unauthenticated MongoDB" that has
been mass-scanned and ransomed since at least 2017.

What this flags
---------------
* mongod YAML config (`/etc/mongod.conf` shape) with
  `security.authorization: disabled` (or `"disabled"`).
* mongod YAML config that is missing the `security` block entirely
  AND contains a `net:` block (i.e. it is a real mongod config),
  reported once as `mongodb-config-no-security-block`.
* CLI / Dockerfile / docker-compose / shell shapes:
  - `mongod --noauth` flag.
  - Absence of `--auth` next to `mongod` invocation in shell or
    Dockerfile `CMD`/`ENTRYPOINT` JSON-array form (reported as
    `mongodb-cli-no-auth-flag`).
* docker-compose / k8s env shape:
  - `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`
    *unset* in a `mongo`/`mongod` service, AND no `--auth` in
    the `command:` — reported as `mongodb-compose-no-root-creds`.

What this does NOT flag
-----------------------
* mongod configs with `security.authorization: enabled`.
* Shell / CMD lines that include `--auth` or `--keyFile`.
* Lines marked with a trailing `# mongo-noauth-ok` comment.
* Patterns inside `#` comments.

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `mongod.conf`, `mongod*.yaml`,
`mongod*.yml`, `Dockerfile*`, `*.Dockerfile`, `docker-compose*.yml`,
`docker-compose*.yaml`, and `*.sh` files.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_SUPPRESS = re.compile(r"#\s*mongo-noauth-ok\b")
RE_AUTHZ_DISABLED = re.compile(
    r"""^\s*authorization\s*:\s*['"]?disabled['"]?\s*(?:#.*)?$""",
    re.IGNORECASE,
)
RE_SECURITY_BLOCK = re.compile(r"^\s*security\s*:\s*(?:#.*)?$", re.IGNORECASE)
RE_NET_BLOCK = re.compile(r"^\s*net\s*:\s*(?:#.*)?$", re.IGNORECASE)
RE_NOAUTH_FLAG = re.compile(r"(?<![A-Za-z0-9_-])--noauth\b")
RE_AUTH_FLAG = re.compile(r"(?<![A-Za-z0-9_-])--auth\b")
RE_KEYFILE_FLAG = re.compile(r"(?<![A-Za-z0-9_-])--keyFile\b")
RE_MONGOD_INVOKE = re.compile(r"\bmongod\b")
RE_COMMENT_LINE = re.compile(r"^\s*#")


def is_yaml_config(path: Path) -> bool:
    name = path.name.lower()
    if name == "mongod.conf":
        return True
    if name.startswith("mongod") and (name.endswith(".yaml") or name.endswith(".yml") or name.endswith(".conf")):
        return True
    return False


def is_dockerfile(path: Path) -> bool:
    n = path.name
    if n == "Dockerfile" or n.startswith("Dockerfile.") or n.endswith(".Dockerfile") or n.endswith(".dockerfile"):
        return True
    return False


def is_compose(path: Path) -> bool:
    n = path.name.lower()
    return (n.startswith("docker-compose") or n.startswith("compose")) and (n.endswith(".yml") or n.endswith(".yaml"))


def is_shell(path: Path) -> bool:
    return path.suffix in (".sh", ".bash")


def scan_yaml_config(path: Path, text: str):
    findings = []
    has_security = False
    has_net = False
    has_authz_disabled_line = False
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        if RE_COMMENT_LINE.match(raw):
            continue
        if RE_SECURITY_BLOCK.match(raw):
            has_security = True
        if RE_NET_BLOCK.match(raw):
            has_net = True
        if RE_AUTHZ_DISABLED.match(raw):
            has_authz_disabled_line = True
            findings.append(
                (path, idx, 1, "mongodb-config-authorization-disabled", raw.strip())
            )
    if has_net and not has_security and not has_authz_disabled_line:
        findings.append(
            (path, 1, 1, "mongodb-config-no-security-block",
             "mongod-style config has net: block but no security: block")
        )
    return findings


def scan_compose(path: Path, text: str):
    """Scan docker-compose for mongo services without auth.

    Heuristic: split into top-level service blocks by 2-space indent
    under `services:`. For each block whose `image:` starts with
    `mongo` (and isn't `mongo-express` etc.), check for absence of
    MONGO_INITDB_ROOT_USERNAME / MONGO_INITDB_ROOT_PASSWORD in the
    block's env, AND absence of `--auth` / `--keyFile` in any
    `command:` line.
    """
    findings = []
    lines = text.splitlines()
    n = len(lines)
    # Find the services: block start
    services_start = None
    for i, raw in enumerate(lines):
        if re.match(r"^services\s*:\s*(?:#.*)?$", raw):
            services_start = i + 1
            break
    if services_start is None:
        return findings
    # Identify per-service sub-blocks (indent == 2 under services)
    i = services_start
    while i < n:
        raw = lines[i]
        m = re.match(r"^  ([A-Za-z0-9_.-]+)\s*:\s*(?:#.*)?$", raw)
        if m:
            svc_name = m.group(1)
            svc_start = i
            j = i + 1
            block_lines = []
            while j < n:
                nxt = lines[j]
                if nxt.strip() == "" or nxt.startswith("    ") or nxt.startswith("\t"):
                    block_lines.append((j + 1, nxt))
                    j += 1
                elif re.match(r"^  [A-Za-z0-9_.-]+\s*:", nxt):
                    break
                elif re.match(r"^\S", nxt):
                    break
                else:
                    block_lines.append((j + 1, nxt))
                    j += 1
            # Inspect this service block
            block_text = "\n".join(b for _, b in block_lines)
            img_m = re.search(r"^\s*image\s*:\s*['\"]?([A-Za-z0-9_./:-]+)", block_text, re.MULTILINE)
            if img_m:
                img = img_m.group(1).lower()
                base = img.split(":", 1)[0].split("/")[-1]
                if base == "mongo" or base == "mongod":
                    suppressed_block = any(RE_SUPPRESS.search(b) for _, b in block_lines)
                    if not suppressed_block:
                        has_user = bool(re.search(r"MONGO_INITDB_ROOT_USERNAME", block_text))
                        has_pass = bool(re.search(r"MONGO_INITDB_ROOT_PASSWORD", block_text))
                        has_auth_in_cmd = bool(RE_AUTH_FLAG.search(block_text)) or bool(RE_KEYFILE_FLAG.search(block_text))
                        has_noauth = bool(RE_NOAUTH_FLAG.search(block_text))
                        if has_noauth:
                            findings.append(
                                (path, svc_start + 1, 1,
                                 "mongodb-compose-noauth-flag",
                                 f"service {svc_name!r} uses --noauth")
                            )
                        if not (has_user and has_pass) and not has_auth_in_cmd:
                            findings.append(
                                (path, svc_start + 1, 1,
                                 "mongodb-compose-no-root-creds",
                                 f"service {svc_name!r} mongo image without ROOT creds and no --auth")
                            )
            i = j
        else:
            i += 1
    return findings


def scan_shell_or_dockerfile(path: Path, text: str):
    findings = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        if RE_SUPPRESS.search(raw):
            continue
        if RE_COMMENT_LINE.match(raw):
            continue
        if RE_NOAUTH_FLAG.search(raw):
            findings.append(
                (path, idx, 1, "mongodb-cli-noauth-flag", raw.strip())
            )
            continue
        if RE_MONGOD_INVOKE.search(raw):
            # Ignore lines that are clearly install/apt/comment-like
            if re.search(r"\b(apt-get|apt|yum|dnf|brew|pip|npm|wget|curl|chmod|chown|mkdir|cp|mv|rm|ls)\b", raw):
                continue
            # Ignore mongod.conf path references
            if "mongod.conf" in raw and "--config" in raw:
                # Config-driven; trust the conf scan
                continue
            if not RE_AUTH_FLAG.search(raw) and not RE_KEYFILE_FLAG.search(raw):
                findings.append(
                    (path, idx, 1, "mongodb-cli-no-auth-flag", raw.strip())
                )
    return findings


def iter_targets(roots):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if not sub.is_file():
                    continue
                if (is_yaml_config(sub) or is_dockerfile(sub)
                        or is_compose(sub) or is_shell(sub)):
                    yield sub
        elif p.is_file():
            yield p


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if is_compose(path):
        return scan_compose(path, text)
    if is_yaml_config(path):
        return scan_yaml_config(path, text)
    if is_dockerfile(path) or is_shell(path):
        return scan_shell_or_dockerfile(path, text)
    return []


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
