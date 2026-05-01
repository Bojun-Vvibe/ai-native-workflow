#!/usr/bin/env python3
"""
llm-output-vault-dev-mode-detector

Flags HashiCorp Vault deployments that run the server in `-dev` mode.
Dev mode:
  * stores everything in-memory (data is lost on restart),
  * starts unsealed with a single root token printed to the log,
  * disables TLS by default and binds to 127.0.0.1:8200,
  * is documented by HashiCorp as "ONLY for development".

When this slips into a Dockerfile, docker-compose stack, Helm chart,
Kubernetes manifest, systemd unit, or shell script that the team
actually deploys, all secrets handed to the cluster live in RAM behind
a fixed, well-known root token. That is a credential-store bypass, not
a "dev convenience".

Maps to:
- CWE-798: Use of Hard-coded Credentials (the dev root token is fixed
  per-process and printed to logs).
- CWE-1188: Insecure Default Initialization of Resource.
- CWE-256 / CWE-257: Plaintext / Recoverable storage of credentials
  (in-memory store with predictable bootstrap).

LLMs reach for `vault server -dev` because every "5-minute Vault
tutorial" on the internet uses it, and because production Vault setup
(seal config, storage backend, TLS, audit) is multi-page.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
Dockerfile, *.yaml, *.yml, *.sh, *.bash, *.service, *.hcl, *.tf,
docker-compose.* and Helm template files).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.

Heuristic
---------
We flag any of the following textual occurrences (outside `#` / `//`
comments):

1. `vault server -dev`            -- the canonical CLI form, optionally
                                     followed by `-dev-root-token-id=...`
                                     or `-dev-listen-address=...`.
2. `vault server --dev`           -- GNU-style.
3. `command: ["vault", "server", "-dev"]`  (compose / k8s exec form).
4. `args: ["server", "-dev"]`     (k8s container args).
5. `VAULT_DEV_ROOT_TOKEN_ID=...`  -- env var that is only meaningful
                                     when the server is in dev mode.
6. `VAULT_DEV_LISTEN_ADDRESS=...` -- same surface.

Each occurrence emits one finding line.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# `vault server -dev` (also matches `--dev`, `-dev-root-token-id`, etc.
# because we anchor on the `-dev` token boundary).
_VAULT_SERVER_DEV = re.compile(
    r"""\bvault\s+server\b[^\n#]*?(?<![\w-])-{1,2}dev(?:-[a-z-]+)?\b"""
)

# Compose / k8s exec form: ["vault","server","-dev"] etc. We keep this
# loose so JSON arrays, YAML flow sequences, and shell wrappers all hit.
_VAULT_EXEC_DEV = re.compile(
    r"""["']vault["']\s*,\s*["']server["']\s*,\s*["']-{1,2}dev(?:-[a-z-]+)?["']"""
)

# k8s container `args:` where the first token is `server` and a later
# token is `-dev` / `--dev`. We just look for `server` and `-dev` close
# together inside an args list.
_K8S_ARGS_DEV = re.compile(
    r"""\bargs\s*:\s*\[[^\]]*["']server["'][^\]]*["']-{1,2}dev(?:-[a-z-]+)?["'][^\]]*\]"""
)

# Env vars that are only meaningful in dev mode.
_DEV_ENV = re.compile(
    r"""\bVAULT_DEV_(?:ROOT_TOKEN_ID|LISTEN_ADDRESS)\b\s*[:=]"""
)

_COMMENT_LINE = re.compile(r"""^\s*(#|//)""")


def _strip_comment(line: str) -> str:
    # Remove trailing `#` comments outside quotes (best effort: we do
    # not parse shell quoting fully, but Vault config files rarely use
    # `#` inside literal strings).
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def scan_text(text: str, path: str) -> List[str]:
    findings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _COMMENT_LINE.match(raw):
            continue
        line = _strip_comment(raw)

        if _VAULT_SERVER_DEV.search(line):
            findings.append(
                f"{path}:{lineno}: vault server running in -dev mode "
                f"(CWE-798/CWE-1188, in-memory store + fixed root token): "
                f"{raw.strip()[:160]}"
            )
            continue
        if _VAULT_EXEC_DEV.search(line):
            findings.append(
                f"{path}:{lineno}: vault exec form invokes -dev mode "
                f"(CWE-798/CWE-1188): {raw.strip()[:160]}"
            )
            continue
        if _K8S_ARGS_DEV.search(line):
            findings.append(
                f"{path}:{lineno}: kubernetes args[] launches `vault "
                f"server -dev` (CWE-798/CWE-1188): {raw.strip()[:160]}"
            )
            continue
        if _DEV_ENV.search(line):
            findings.append(
                f"{path}:{lineno}: VAULT_DEV_* env var set -- only "
                f"meaningful in dev mode (CWE-798): {raw.strip()[:160]}"
            )
            continue
    return findings


_TARGET_NAMES = (
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
)
_TARGET_EXTS = (
    ".yaml", ".yml", ".sh", ".bash", ".service", ".hcl",
    ".tf", ".tpl", ".env",
)


def iter_paths(roots: Iterable[str]) -> Iterable[str]:
    for r in roots:
        if os.path.isdir(r):
            for dp, _dn, fn in os.walk(r):
                for f in fn:
                    low = f.lower()
                    if low in _TARGET_NAMES or low.startswith("dockerfile"):
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
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write(f"warn: cannot read {path}: {e}\n")
            continue
        for line in scan_text(text, path):
            print(line)
            any_finding = True
    return 1 if any_finding else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
