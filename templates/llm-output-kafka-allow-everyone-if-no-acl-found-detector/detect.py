#!/usr/bin/env python3
"""
llm-output-kafka-allow-everyone-if-no-acl-found-detector

Flags Apache Kafka broker configs that set the dangerous combination

  allow.everyone.if.no.acl.found = true

This setting tells Kafka's ACL authorizer:

  > "If a resource (topic / consumer group / cluster) has *no* ACL
  >  attached, allow everyone to do everything to it."

In a cluster where most topics are auto-created or where ACLs are
applied piecemeal, this collapses the entire authorization model:
any authenticated principal (and, depending on the listener, any
unauthenticated PLAINTEXT client) can produce / consume / delete
topics that simply happen to have no ACL row.

The Confluent / Apache Kafka security docs flag this explicitly:

  > "The default value (false) is the safe choice. Setting
  >  allow.everyone.if.no.acl.found=true effectively disables
  >  authorization for any new resource and is strongly
  >  discouraged in production."
  >  -- https://kafka.apache.org/documentation/#security_authz

Maps to:

  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-1188: Insecure Default Initialization of Resource
  - OWASP A05:2021 Security Misconfiguration

Why LLMs ship this
------------------
Tutorials and Stack Overflow answers routinely set
``allow.everyone.if.no.acl.found=true`` to "fix" a
``TopicAuthorizationException`` that the user hits while following
along. Models then suggest the same one-line fix in production
configs, helm values, and docker-compose envs without flagging the
blast radius.

Heuristic
---------
Three concrete forms (case-insensitive on the key, the value must
literally be the word ``true``):

1. **Java properties** (``server.properties``,
   ``kafka.properties``):

     allow.everyone.if.no.acl.found=true

2. **YAML** (Strimzi / Helm values, docker-compose):

     allow.everyone.if.no.acl.found: "true"
     allowEveryoneIfNoAclFound: true       # camelCase variant
     KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND: "true"   # env style

3. **CLI / env / Dockerfile**:

     -Dallow.everyone.if.no.acl.found=true
     KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND=true
     export KAFKA_OPTS="... -Dallow.everyone.if.no.acl.found=true"

We do NOT flag:

  * the same key set to ``false`` (the safe default),
  * comments or docs that mention the bad pattern,
  * configs that omit the key entirely (default is ``false``).

Stdlib-only. Walks dirs, scans ``*.properties``, ``*.conf``,
``*.yaml``, ``*.yml``, ``*.env``, ``*.sh``, ``*.bash``,
``*.service``, ``Dockerfile*``, ``docker-compose.*``, and any file
whose basename starts with ``kafka`` or ``server.properties``.

Exit codes: 0 = clean, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

_COMMENT_LINE = re.compile(r"""^\s*(?://|#|;)""")

# Java properties: key = value, where key is dotted form.
_PROP_DOTTED = re.compile(
    r"""^\s*allow\.everyone\.if\.no\.acl\.found\s*[:=]\s*true\b""",
    re.IGNORECASE,
)

# YAML form: dotted key as quoted YAML key, OR camelCase, OR env-style
# uppercase. Match a YAML mapping line where the value is true / "true".
_YAML_DOTTED = re.compile(
    r"""^\s*["']?allow\.everyone\.if\.no\.acl\.found["']?\s*:\s*"""
    r"""["']?true["']?\s*(?:#.*)?$""",
    re.IGNORECASE,
)
_YAML_CAMEL = re.compile(
    r"""^\s*allowEveryoneIfNoAclFound\s*:\s*["']?true["']?\s*(?:#.*)?$""",
)
_YAML_ENV_STYLE = re.compile(
    r"""^\s*KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND\s*:\s*"""
    r"""["']?true["']?\s*(?:#.*)?$""",
)

# CLI / env: -Dkey=true OR KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND=true
# in shell / Dockerfile / systemd contexts.
_CLI_DPROP = re.compile(
    r"""-D\s*allow\.everyone\.if\.no\.acl\.found\s*=\s*true\b""",
    re.IGNORECASE,
)
_CLI_ENV = re.compile(
    r"""\bKAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND\s*=\s*["']?true["']?\b""",
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


def _msg(path: str, lineno: int, raw: str, kind: str) -> str:
    return (
        f"{path}:{lineno}: kafka allow.everyone.if.no.acl.found=true "
        f"({kind}) -> any principal can produce/consume/delete any "
        f"resource that has no explicit ACL row "
        f"(CWE-732/CWE-1188): {raw.strip()[:160]}"
    )


def scan_properties(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _PROP_DOTTED.match(raw):
            findings.append(_msg(path, i, raw, "java properties"))
    return findings


def scan_yaml(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        if _YAML_DOTTED.match(raw):
            findings.append(_msg(path, i, raw, "yaml dotted key"))
        elif _YAML_CAMEL.match(raw):
            findings.append(_msg(path, i, raw, "yaml camelCase key"))
        elif _YAML_ENV_STYLE.match(raw):
            findings.append(_msg(path, i, raw, "yaml KAFKA_* env key"))
    return findings


def scan_cli(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_shell_comment(raw)
        if _CLI_DPROP.search(line):
            findings.append(_msg(path, i, raw, "JVM -D flag"))
            continue
        if _CLI_ENV.search(line):
            findings.append(_msg(path, i, raw, "shell/Dockerfile env"))
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
    if low.endswith((".properties", ".conf")):
        out.extend(scan_properties(text, path))
    if low.endswith((".yaml", ".yml")):
        out.extend(scan_yaml(text, path))
        # compose `command:` / `environment:` may carry CLI/env forms.
        out.extend(scan_cli(text, path))
    if low.endswith((".env", ".sh", ".bash", ".service")):
        out.extend(scan_cli(text, path))
    base = os.path.basename(low)
    if base.startswith("dockerfile") or base.startswith("docker-compose") \
            or low.endswith(".dockerfile"):
        out.extend(scan_cli(text, path))
    return out


_TARGET_NAMES = ("dockerfile", "docker-compose.yml", "docker-compose.yaml",
                 "server.properties", "kafka.properties")
_TARGET_EXTS = (".properties", ".conf", ".yaml", ".yml", ".env",
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
                            or low.startswith("kafka") \
                            or low.startswith("server.properties"):
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
