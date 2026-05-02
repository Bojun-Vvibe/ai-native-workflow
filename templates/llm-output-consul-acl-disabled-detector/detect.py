#!/usr/bin/env python3
"""
llm-output-consul-acl-disabled-detector

Flags HashiCorp Consul configurations that **disable ACLs** or set
the default policy to ``allow``. With ACLs disabled (or in default-
allow mode), any client that can reach the Consul HTTP / gRPC / DNS
API can:

  * read every KV pair (often used as an app-config + secret store),
  * register or deregister services (full service-mesh hijack),
  * read the catalog of every node, service, IP, and health check,
  * issue Connect intentions and TLS leaf certs in some setups,
  * snapshot the whole Raft state.

The Consul docs say it bluntly:

> "Production deployments should always set ``default_policy`` to
>  ``deny``. The ``allow`` policy is only intended for development."
>  -- https://developer.hashicorp.com/consul/docs/security/acl

Maps to:
  - CWE-306: Missing Authentication for Critical Function
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Almost every "Consul in 5 minutes" tutorial uses ``-dev`` mode or
sets ``acl { enabled = false }`` so the demo Just Works. Models
copy that block straight into a production ``consul.hcl`` /
docker-compose / k8s manifest.

Heuristic
---------
Three concrete forms:

1. **HCL** (``consul.hcl``, ``server.hcl``):

     acl {
       enabled        = false
     }

   or

     acl = {
       enabled        = true
       default_policy = "allow"
     }

2. **JSON** (``config.json``, ``consul.json``):

     {"acl": {"enabled": false}}
     {"acl": {"enabled": true, "default_policy": "allow"}}

3. **CLI flag / env** (Dockerfile CMD, compose ``command:``,
   k8s ``args:``, systemd ``ExecStart=``, shell wrapper):

     consul agent -dev
     consul agent -server ... (no acl block at all is NOT flagged;
       we only flag explicit disables / default-allow / -dev)

We do NOT flag:

  * ``acl { enabled = true; default_policy = "deny" }`` (correct),
  * configs that simply omit the ``acl`` block (could be set
    elsewhere; we don't want to spam),
  * comments / docs that mention the bad pattern.

Stdlib-only. Walks dirs, scans ``*.hcl``, ``*.json``, ``*.yaml``,
``*.yml``, ``*.env``, ``*.sh``, ``*.bash``, ``*.service``,
``Dockerfile*``, ``docker-compose.*``, and any file whose basename
starts with ``consul``.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# --- HCL ---
# Section header `acl {` or `acl = {` (top-level).
_HCL_ACL_HEADER = re.compile(
    r"""^\s*acl\s*=?\s*\{\s*(?://.*|#.*)?$""", re.IGNORECASE,
)
# Closing brace at column 0-ish (heuristic).
_HCL_CLOSE = re.compile(r"""^\s*\}\s*(?://.*|#.*)?$""")
_HCL_ENABLED_FALSE = re.compile(
    r"""^\s*enabled\s*=\s*false\s*(?://.*|#.*)?$""", re.IGNORECASE,
)
_HCL_DEFAULT_ALLOW = re.compile(
    r"""^\s*default_policy\s*=\s*"allow"\s*(?://.*|#.*)?$""",
    re.IGNORECASE,
)

# --- JSON / inline ---
# We don't fully parse JSON because the file may also be HCL-ish.
# Match `"acl"` block with `"enabled": false` or
# `"default_policy": "allow"` somewhere within ~400 chars.
_JSON_ACL_DISABLED = re.compile(
    r""""acl"\s*:\s*\{[^}]{0,400}?"enabled"\s*:\s*false""",
    re.IGNORECASE | re.DOTALL,
)
_JSON_ACL_ALLOW = re.compile(
    r""""acl"\s*:\s*\{[^}]{0,400}?"default_policy"\s*:\s*"allow"\s*""",
    re.IGNORECASE | re.DOTALL,
)

# --- YAML (helm values style) ---
_YAML_ACL_KEY = re.compile(r"""^(\s*)acl\s*:\s*(?:#.*)?$""")
_YAML_ENABLED_FALSE = re.compile(
    r"""^(\s*)enabled\s*:\s*["']?false["']?\s*(?:#.*)?$""", re.IGNORECASE,
)
_YAML_DEFAULT_ALLOW = re.compile(
    r"""^(\s*)default_?policy\s*:\s*["']?allow["']?\s*(?:#.*)?$""",
    re.IGNORECASE,
)
_YAML_DEDENT_KEY = re.compile(r"""^(\s*)[A-Za-z0-9_.-]+\s*:""")

# --- CLI ---
# `consul agent -dev` (anywhere on the line, but the token must be
# preceded by `consul` somewhere on the same line to avoid matching
# unrelated `-dev` flags).
_CLI_DEV = re.compile(
    r"""\bconsul\b[^\n#]*?\s-dev(?=\s|$|"|')""",
)


def _strip_shell_comment(line: str) -> str:
    out = []
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
    return "".join(out)


def scan_hcl(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    in_acl = False
    depth = 0
    acl_start = 0
    for i, raw in enumerate(lines, start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if not in_acl and _HCL_ACL_HEADER.match(raw):
            in_acl = True
            depth = 1
            acl_start = i
            continue
        if in_acl:
            # Track nested braces crudely.
            depth += raw.count("{") - raw.count("}")
            if _HCL_ENABLED_FALSE.match(raw):
                findings.append(
                    f"{path}:{i}: consul acl.enabled = false (block "
                    f"opened at line {acl_start}) -> open KV/catalog/"
                    f"service-registration (CWE-306/CWE-732): "
                    f"{raw.strip()[:160]}"
                )
            if _HCL_DEFAULT_ALLOW.match(raw):
                findings.append(
                    f"{path}:{i}: consul acl.default_policy = "
                    f'"allow" (block opened at line {acl_start}) -> '
                    f"any token (incl. anonymous) gets full access "
                    f"(CWE-732/CWE-1188): {raw.strip()[:160]}"
                )
            if depth <= 0:
                in_acl = False
                depth = 0
    return findings


def scan_json(text: str, path: str) -> List[str]:
    findings: List[str] = []
    if _JSON_ACL_DISABLED.search(text):
        # Find first matching line for nicer output.
        for i, raw in enumerate(text.splitlines(), start=1):
            if re.search(r'"enabled"\s*:\s*false', raw, re.IGNORECASE):
                findings.append(
                    f"{path}:{i}: consul acl.enabled=false in JSON "
                    f"config -> open KV/catalog (CWE-306): "
                    f"{raw.strip()[:160]}"
                )
                break
    if _JSON_ACL_ALLOW.search(text):
        for i, raw in enumerate(text.splitlines(), start=1):
            if re.search(
                r'"default_policy"\s*:\s*"allow"', raw, re.IGNORECASE,
            ):
                findings.append(
                    f"{path}:{i}: consul acl.default_policy=\"allow\""
                    f" in JSON config -> default-allow ACLs "
                    f"(CWE-732/CWE-1188): {raw.strip()[:160]}"
                )
                break
    return findings


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _YAML_ACL_KEY.match(lines[i])
        if not m:
            i += 1
            continue
        base_indent = len(m.group(1))
        acl_line = i + 1
        j = i + 1
        while j < len(lines):
            line = lines[j]
            if line.strip() == "" or _COMMENT_LINE.match(line):
                j += 1
                continue
            md = _YAML_DEDENT_KEY.match(line)
            if md and len(md.group(1)) <= base_indent:
                break
            mef = _YAML_ENABLED_FALSE.match(line)
            if mef and len(mef.group(1)) > base_indent:
                findings.append(
                    f"{path}:{j+1}: consul acl: enabled: false under "
                    f"acl: block (line {acl_line}) -> open KV/catalog"
                    f" (CWE-306/CWE-732)"
                )
            mda = _YAML_DEFAULT_ALLOW.match(line)
            if mda and len(mda.group(1)) > base_indent:
                findings.append(
                    f"{path}:{j+1}: consul acl: default_policy: allow"
                    f" under acl: block (line {acl_line}) -> default-"
                    f"allow ACLs (CWE-732/CWE-1188)"
                )
            j += 1
        i = j if j > i else i + 1
    return findings


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        if _CLI_DEV.search(line):
            findings.append(
                f"{path}:{lineno}: `consul agent -dev` runs an in-"
                f"memory agent with ACLs disabled and HTTP open on "
                f":8500 (CWE-306/CWE-1188): {raw.strip()[:160]}"
            )
    return findings


def scan(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write(f"warn: cannot read {path}: {e}\n")
        return []
    low = path.lower()
    out: List[str] = []
    if low.endswith(".hcl"):
        out.extend(scan_hcl(text, path))
    if low.endswith(".json"):
        out.extend(scan_json(text, path))
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
        out.extend(scan_cli(text, path))
    if low.endswith((".env", ".sh", ".bash", ".service")):
        out.extend(scan_cli(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose") \
            or low.endswith(".dockerfile"):
        out.extend(scan_cli(text, path))
    return out


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml")
_TARGET_EXTS = (".hcl", ".json", ".yaml", ".yml", ".env",
                ".sh", ".bash", ".service", ".dockerfile")


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES \
                            or low.startswith("dockerfile") \
                            or low.startswith("docker-compose") \
                            or low.startswith("consul"):
                        yield os.path.join(dp, f)
                    elif low.endswith(_TARGET_EXTS):
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
