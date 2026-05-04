#!/usr/bin/env python3
"""
llm-output-docker-registry-no-auth-htpasswd-detector

Flags Docker `registry:2` (distribution/distribution) deployments that
ship a `config.yml` (or env-driven equivalent) WITHOUT any
authentication backend configured. The official Docker registry image
defaults to **no auth** -- anyone who can reach the listen address
can `docker push`, `docker pull`, list repositories via
`/v2/_catalog`, and delete images via the DELETE manifest endpoint
(when `delete.enabled = true`).

Reference:
  https://distribution.github.io/distribution/about/configuration/#auth
  https://distribution.github.io/distribution/about/deploying/#native-basic-auth

The supported `auth:` backends are:

  auth:
    silly:    {...}    -- explicitly disables all auth ("for testing")
    token:    {...}    -- delegated bearer token (Harbor / oauth2)
    htpasswd: {...}    -- in-process basic auth against an htpasswd file
    none:     {...}    -- explicitly disables auth (some forks)

A registry with NO `auth:` key, or with `auth: {}`, or with
`auth: { silly: {...} }`, or with `auth: { none: {...} }` is open.

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-287: Improper Authentication
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A07:2021 Identification and Authentication Failures

Why LLMs ship this
------------------
The Docker docs' "Deploy a registry server" 5-minute tutorial is:

    docker run -d -p 5000:5000 --name registry registry:2

That image's baked-in `/etc/docker/registry/config.yml` has no
`auth:` block. Every "self-hosted registry" blog post copies that
command, sometimes wrapping it with `--restart=always`, and ships
to prod. The model reproduces the same.

Heuristic
---------
We scan YAML files whose basename matches:

  * `config.yml`, `config.yaml`
  * `registry-config.*`, `*registry*.yml`, `*registry*.yaml`
  * `docker-compose.yml` / `docker-compose.yaml` (look at services
    that use `image: registry:*` or `image: distribution/*` and
    check whether `REGISTRY_AUTH*` env vars are set OR a config
    volume is mounted with auth-bearing content -- best-effort).

For a registry-shaped config file (we recognise it by the presence
of a top-level `version:` key alongside `storage:` or `http:`), we
require:

  auth:
    htpasswd: { realm: <str>, path: <str> }
        -- OR --
    token:    { realm: <url>, service: <str>, issuer: <str>,
                rootcertbundle: <path> }

If `auth:` is missing, empty, or only contains `silly:` / `none:`,
the file is flagged.

For docker-compose files, we ALSO flag any service with
`image: registry:*` (or `image: distribution/distribution:*`) that
has no `REGISTRY_AUTH=htpasswd` / `REGISTRY_AUTH=token` env var and
no mounted `/auth/htpasswd` volume.

Stdlib-only. No yaml lib -- we use a small indentation-aware parser.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------
# tiny indentation-aware YAML reader (we only need top-level / nested keys)
# --------------------------------------------------------------------------

_KEY_LINE = re.compile(
    r"""^(?P<indent>[ ]*)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*"""
    r"""(?P<rest>.*)$""",
)
_LIST_ITEM = re.compile(r"""^(?P<indent>[ ]*)-\s+""")
_COMMENT_ONLY = re.compile(r"""^\s*#""")
_BLANK = re.compile(r"""^\s*$""")


def _strip_inline_comment(s: str) -> str:
    # naive: split on " #" outside of quotes -- good enough for config.yml
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d \
                and (i == 0 or s[i - 1].isspace()):
            break
        out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _walk_keys(text: str) -> List[Tuple[int, int, str, str]]:
    """Return list of (lineno, indent, key, rest) for every key-shaped
    line, ignoring comments and list items."""
    out: List[Tuple[int, int, str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _BLANK.match(raw) or _COMMENT_ONLY.match(raw):
            continue
        if _LIST_ITEM.match(raw):
            continue
        line = _strip_inline_comment(raw)
        m = _KEY_LINE.match(line)
        if not m:
            continue
        out.append((lineno, len(m.group("indent")),
                    m.group("key"), m.group("rest").strip()))
    return out


def _children_of(keys: List[Tuple[int, int, str, str]],
                 idx: int) -> List[Tuple[int, int, str, str]]:
    """Direct children (and deeper, until indent <= parent) of keys[idx]."""
    parent_indent = keys[idx][1]
    out = []
    j = idx + 1
    while j < len(keys):
        if keys[j][1] <= parent_indent:
            break
        out.append(keys[j])
        j += 1
    return out


def _direct_children(keys: List[Tuple[int, int, str, str]],
                     idx: int) -> List[Tuple[int, int, str, str]]:
    parent_indent = keys[idx][1]
    out = []
    child_indent: Optional[int] = None
    j = idx + 1
    while j < len(keys):
        ind = keys[j][1]
        if ind <= parent_indent:
            break
        if child_indent is None:
            child_indent = ind
        if ind == child_indent:
            out.append(keys[j])
        j += 1
    return out


def _find_top_level(keys: List[Tuple[int, int, str, str]],
                    name: str) -> Optional[int]:
    for i, (_lineno, indent, key, _rest) in enumerate(keys):
        if indent == 0 and key == name:
            return i
    return None


# --------------------------------------------------------------------------
# registry config.yml shape detection
# --------------------------------------------------------------------------


def _looks_like_registry_config(keys: List[Tuple[int, int, str, str]]) -> bool:
    has_version = _find_top_level(keys, "version") is not None
    has_storage = _find_top_level(keys, "storage") is not None
    has_http = _find_top_level(keys, "http") is not None
    # require version + (storage or http). Avoids false-positives on
    # random YAMLs that happen to have "auth:" in them.
    return has_version and (has_storage or has_http)


_AUTH_BACKENDS_OK = {"htpasswd", "token"}
_AUTH_BACKENDS_OPEN = {"silly", "none"}


def scan_registry_config(text: str, path: str) -> List[str]:
    keys = _walk_keys(text)
    if not _looks_like_registry_config(keys):
        return []
    findings: List[str] = []

    auth_idx = _find_top_level(keys, "auth")
    if auth_idx is None:
        findings.append(
            f"{path}:1: docker registry config has no top-level `auth:` "
            f"block -> anonymous push/pull on /v2/* (CWE-306). Add "
            f"`auth: { '{' } htpasswd: { '{' } realm: ..., path: "
            f"/auth/htpasswd { '}' } { '}' }` or `auth.token`."
        )
        return findings

    children = _direct_children(keys, auth_idx)
    if not children:
        findings.append(
            f"{path}:{keys[auth_idx][0]}: docker registry `auth:` block "
            f"is empty -> anonymous push/pull on /v2/* (CWE-306)."
        )
        return findings

    backend_names = {c[2] for c in children}
    has_ok = bool(backend_names & _AUTH_BACKENDS_OK)
    has_open = bool(backend_names & _AUTH_BACKENDS_OPEN)

    if has_open and not has_ok:
        backend = sorted(backend_names & _AUTH_BACKENDS_OPEN)[0]
        findings.append(
            f"{path}:{keys[auth_idx][0]}: docker registry uses "
            f"`auth.{backend}` -> explicitly disables authentication "
            f"(CWE-1188/CWE-306). Replace with `auth.htpasswd` or "
            f"`auth.token`."
        )
        return findings

    if not has_ok:
        backends = ", ".join(sorted(backend_names)) or "<none>"
        findings.append(
            f"{path}:{keys[auth_idx][0]}: docker registry `auth:` "
            f"contains only unsupported backend(s) [{backends}] -> "
            f"anonymous push/pull (CWE-287)."
        )
    return findings


# --------------------------------------------------------------------------
# docker-compose pass: services using registry:2 image without
# REGISTRY_AUTH env var
# --------------------------------------------------------------------------

_COMPOSE_REGISTRY_IMAGE = re.compile(
    r"""^\s*image\s*:\s*['"]?(?:docker\.io/library/)?"""
    r"""(?:registry|distribution/distribution)(?::[\w.-]+)?['"]?\s*"""
    r"""(?:#.*)?$""",
    re.IGNORECASE | re.MULTILINE,
)
_REGISTRY_AUTH_ENV = re.compile(
    r"""REGISTRY_AUTH(?:=|:)\s*['"]?(htpasswd|token)['"]?""",
    re.IGNORECASE,
)


def _scan_compose(text: str, path: str) -> List[str]:
    findings: List[str] = []
    keys = _walk_keys(text)
    services_idx = _find_top_level(keys, "services")
    if services_idx is None:
        return []
    # service entries are direct children of services:
    service_entries = _direct_children(keys, services_idx)
    for s_idx_in_keys in [keys.index(s) for s in service_entries]:
        svc = keys[s_idx_in_keys]
        svc_name = svc[2]
        # Look only inside this service's subtree
        subtree = _children_of(keys, s_idx_in_keys)
        # Determine subtree line range to inspect raw text for image/env.
        if not subtree:
            continue
        first_ln = svc[0]
        # find next sibling at same indent <= svc indent (or EOF)
        last_ln = len(text.splitlines())
        for k in keys[s_idx_in_keys + 1:]:
            if k[1] <= svc[1]:
                last_ln = k[0] - 1
                break
        block = "\n".join(text.splitlines()[first_ln - 1:last_ln])
        if not _COMPOSE_REGISTRY_IMAGE.search(block):
            continue
        # Has the block configured auth either via env var or via a
        # mounted /auth dir or REGISTRY_AUTH_TOKEN_REALM ?
        if _REGISTRY_AUTH_ENV.search(block):
            continue
        if "REGISTRY_AUTH_TOKEN_REALM" in block:
            continue
        # Check for an htpasswd file mount
        if re.search(r"""/auth/htpasswd""", block):
            # Mount alone is not enough -- env var must select it. Still
            # warn but mention.
            findings.append(
                f"{path}:{first_ln}: docker-compose service `{svc_name}` "
                f"uses registry:2 image and mounts /auth/htpasswd but "
                f"does NOT set REGISTRY_AUTH=htpasswd -> registry will "
                f"start with auth disabled (CWE-1188)."
            )
            continue
        findings.append(
            f"{path}:{first_ln}: docker-compose service `{svc_name}` "
            f"runs registry:2 image with no REGISTRY_AUTH env var and "
            f"no auth config mount -> anonymous push/pull on /v2/* "
            f"(CWE-306)."
        )
    return findings


# --------------------------------------------------------------------------
# entrypoints
# --------------------------------------------------------------------------


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    base = os.path.basename(path).lower()
    out: List[str] = []
    if not base.endswith((".yml", ".yaml")):
        return out
    # docker-compose detection: filename hint OR top-level `services:`
    # alongside `version:` (and no top-level `storage:`/`http:` which
    # would indicate a registry config).
    keys = _walk_keys(text)
    has_services = _find_top_level(keys, "services") is not None
    has_storage = _find_top_level(keys, "storage") is not None
    has_http = _find_top_level(keys, "http") is not None
    looks_compose = base.startswith("docker-compose") or (
        has_services and not (has_storage or has_http)
    )
    if looks_compose:
        out.extend(_scan_compose(text, path))
    else:
        out.extend(scan_registry_config(text, path))
    return out


_TARGETS = (".yml", ".yaml")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    if f.lower().endswith(_TARGETS):
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
