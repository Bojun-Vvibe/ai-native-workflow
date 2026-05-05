#!/usr/bin/env python3
"""Detect HashiCorp Vault configurations that turn off mlock memory
protection across four common config surfaces:

* ``vault.hcl`` / ``config.hcl`` (HCL)
* Helm ``values.yaml`` (``server.disableMlock`` toggle and
  embedded-HCL ``extraConfig`` blocks)
* ``docker-compose.yml`` env (``VAULT_DISABLE_MLOCK=true``)
* ``Dockerfile`` / shell ``ENV`` lines

Suppression: a magic comment ``# vault-disable-mlock-allowed``
silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*vault-disable-mlock-allowed")

TRUTHY = {"true", "1", "yes", "on"}


def _is_truthy(value: str) -> bool:
    v = value.strip().strip("'").strip('"').strip()
    return v.lower() in TRUTHY


# --- HCL --------------------------------------------------------------

HCL_KV = re.compile(
    r"""(?ix)
    ^\s*
    disable_mlock
    \s*=\s*
    (['"]?)([^'"\s#/]+)\1
    \s*(?:[#/].*)?$
    """
)


def _scan_hcl(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = HCL_KV.match(raw)
        if not m:
            continue
        val = m.group(2)
        if _is_truthy(val):
            findings.append(
                (i, f"vault disable_mlock = {val!r} drops mlock memory protection")
            )
    return findings


# --- ENV / Dockerfile -------------------------------------------------

ENV_VAULT = re.compile(
    r"""(?ix)
    (?:^|[\s])
    (?:ENV\s+|ARG\s+|export\s+|-\s+)?
    VAULT_DISABLE_MLOCK
    \s*[=\s]\s*
    (['"]?)([^'"\s]+)\1
    """
)


def _scan_envish(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw
        if "#" in line:
            line = re.sub(r"(?:^|\s)#.*$", "", line)
        m = ENV_VAULT.search(line)
        if not m:
            continue
        val = m.group(2)
        if _is_truthy(val):
            findings.append(
                (i, f"VAULT_DISABLE_MLOCK={val!r} drops mlock memory protection")
            )
    return findings


# --- YAML (Helm values) ----------------------------------------------

YAML_KV = re.compile(
    r"""(?x)
    ^\s*
    (disableMlock|disable_mlock)
    \s*:\s*
    (['"]?)([^'"\n#]+?)\2
    \s*(?:\#.*)?$
    """
)


def _scan_yaml(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = YAML_KV.match(raw)
        if not m:
            continue
        key = m.group(1)
        val = m.group(3).strip()
        if _is_truthy(val):
            findings.append(
                (i, f"vault helm {key}: {val!r} drops mlock memory protection")
            )
    # Helm chart often inlines HCL inside server.extraConfig: |
    # so also try the HCL scan over the same source.
    for line, reason in _scan_hcl(source):
        findings.append((line, reason))
    # de-dup
    findings = sorted({(l, r) for l, r in findings})
    return findings


def _classify(path: Path, source: str) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name == "dockerfile" or suffix == ".dockerfile" or name.startswith("dockerfile."):
        return "envish"
    if suffix in (".hcl",):
        return "hcl"
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if suffix in (".envfile", ".sh", ".bash", ".service", ".conf"):
        return "envish"
    # Heuristic on contents.
    if re.search(r"^\s*disable_mlock\s*=", source, re.M):
        return "hcl"
    if re.search(r"^\s*disableMlock\s*:", source, re.M):
        return "yaml"
    if "VAULT_DISABLE_MLOCK" in source:
        return "envish"
    return "hcl"


def scan(source: str, path: Path = Path("<stdin>")) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    kind = _classify(path, source)
    if kind == "hcl":
        return _scan_hcl(source)
    if kind == "yaml":
        a = _scan_yaml(source)
        b = _scan_envish(source)
        merged = {(line, reason) for line, reason in a + b}
        return sorted(merged)
    return _scan_envish(source)


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in (
                "*.hcl",
                "values.yaml", "values.yml",
                "docker-compose*.yml", "docker-compose*.yaml",
                "Dockerfile", "Dockerfile.*", "*.dockerfile",
                "*.envfile", "*.sh",
            ):
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
        hits = scan(source, f)
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
