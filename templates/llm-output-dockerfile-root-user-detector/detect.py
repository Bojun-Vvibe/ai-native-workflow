#!/usr/bin/env python3
"""Detect Dockerfiles that run as root.

A Dockerfile that never drops to a non-root user, or that explicitly
sets `USER root` / `USER 0` near the end of its build, ships a
container whose entrypoint runs as uid 0 by default. Inside the
container that is "just root", but combined with common operational
patterns — bind-mounted host paths, shared kernels, missing
`no-new-privileges` flags, capability defaults — it widens the blast
radius of any RCE in the workload to the host's docker group.

LLMs love to emit Dockerfiles that copy code, `RUN pip install`, and
go straight to `CMD ["python", "app.py"]` with no `USER` directive.
The same pattern shows up when an early `USER nonroot` is overridden
by a later `USER root` for a `RUN apt-get install` step but the
author forgets to drop again.

What this flags
---------------
* `USER root` (case-insensitive) anywhere in the file.
* `USER 0` / `USER 0:0` / `USER 0:<group>`.
* Any Dockerfile that contains a `FROM` instruction but no `USER`
  directive at all (reported once per file as `dockerfile-no-user`).
* The *effective final user is root* condition: the LAST `USER`
  directive in the file is `root` / `0`.

What this does NOT flag
-----------------------
* Dockerfiles whose final `USER` is a non-root name or non-zero uid.
* Lines marked with a trailing `# docker-root-ok` comment.
* `USER root` inside a `# ...` comment.
* Multi-stage builds where an intermediate stage runs as root but
  the final stage drops to a non-root user (we evaluate per-stage
  using `FROM` boundaries; the *last* stage is the one shipped).

Usage
-----
    python3 detect.py <file_or_dir> [...]

Exit code 1 if any findings, 0 otherwise. python3 stdlib only.
Recurses directories looking for `Dockerfile`, `Dockerfile.*`,
`*.Dockerfile`, and `Containerfile`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


RE_USER = re.compile(r"^\s*USER\s+(\S+)\s*(?:#.*)?$", re.IGNORECASE)
RE_FROM = re.compile(r"^\s*FROM\s+\S+", re.IGNORECASE)
RE_SUPPRESS = re.compile(r"#\s*docker-root-ok\b")
RE_COMMENT = re.compile(r"^\s*#")


def is_root_user(token: str) -> bool:
    t = token.strip().strip('"').strip("'")
    if t.lower() == "root":
        return True
    if t == "0":
        return True
    # uid:gid forms — root if uid is 0 or "root"
    if ":" in t:
        uid = t.split(":", 1)[0]
        if uid == "0" or uid.lower() == "root":
            return True
    return False


def is_dockerfile(path: Path) -> bool:
    name = path.name
    if name == "Dockerfile" or name == "Containerfile":
        return True
    if name.startswith("Dockerfile.") or name.startswith("Containerfile."):
        return True
    if name.endswith(".Dockerfile") or name.endswith(".dockerfile"):
        return True
    return False


def scan_dockerfile(path: Path, text: str) -> list[tuple[Path, int, int, str, str]]:
    findings: list[tuple[Path, int, int, str, str]] = []
    lines = text.splitlines()
    has_from = False
    # per-stage tracking
    stages: list[dict] = []
    cur: dict | None = None
    suppressed: set[int] = set()

    for idx, raw in enumerate(lines, start=1):
        if RE_SUPPRESS.search(raw):
            suppressed.add(idx)
            continue
        if RE_COMMENT.match(raw):
            continue

        if RE_FROM.match(raw):
            has_from = True
            cur = {"start": idx, "users": []}
            stages.append(cur)
            continue

        m = RE_USER.match(raw)
        if m:
            tok = m.group(1)
            if cur is None:
                cur = {"start": 0, "users": []}
                stages.append(cur)
            cur["users"].append((idx, tok, raw))

    if not has_from:
        return findings

    final_stage = stages[-1] if stages else None
    if final_stage is None:
        return findings

    # Flag every explicit USER root in the FINAL stage only.
    final_users = final_stage["users"]
    for idx, tok, raw in final_users:
        if idx in suppressed:
            continue
        if is_root_user(tok):
            col = raw.lower().find("user") + 1 if "user" in raw.lower() else 1
            findings.append(
                (path, idx, col, "dockerfile-user-root-explicit", raw.strip())
            )

    if not final_users:
        # No USER in the final stage — defaults to root.
        findings.append(
            (path, final_stage["start"], 1,
             "dockerfile-no-user", "final stage has no USER directive")
        )
    else:
        last_idx, last_tok, last_raw = final_users[-1]
        if is_root_user(last_tok) and last_idx not in suppressed:
            findings.append(
                (path, last_idx, 1, "dockerfile-final-user-root",
                 f"final USER is {last_tok!r}")
            )
    return findings


def iter_targets(roots: list[str]):
    for r in roots:
        p = Path(r)
        if p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and is_dockerfile(sub):
                    yield sub
        elif p.is_file():
            yield p


def scan_file(path: Path) -> list[tuple[Path, int, int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if is_dockerfile(path):
        return scan_dockerfile(path, text)
    return []


def main(argv: list[str]) -> int:
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
