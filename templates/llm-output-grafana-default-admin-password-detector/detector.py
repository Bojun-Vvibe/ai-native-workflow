#!/usr/bin/env python3
"""Detect Grafana configurations that leave the built-in admin account
on its default password (or a placeholder like ``change-me``) across
four config surfaces:

* ``grafana.ini`` / ``custom.ini`` (INI)
* ``docker-compose.yml`` env (YAML)
* Helm ``values.yaml`` (YAML)
* ``Dockerfile`` / shell ``ENV`` lines

The insecure shape we flag:

* ``[security] admin_password = admin`` (or one of the canonical
  defaults: ``admin``, ``password``, ``grafana``, ``change-me``,
  ``changeme``, ``CHANGE_ME``).
* ``GF_SECURITY_ADMIN_PASSWORD=admin`` in compose env, Dockerfile
  ``ENV`` / ``ARG``, or shell exports.
* Helm ``adminPassword: admin`` (or canonical defaults) at any
  nesting level.

Suppression: a magic comment ``# grafana-default-admin-password-allowed``
silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*grafana-default-admin-password-allowed")

# Canonical insecure defaults / common placeholders.
DEFAULT_PASSWORDS = {
    "admin",
    "password",
    "grafana",
    "change-me",
    "changeme",
    "change_me",
}


def _is_default(value: str) -> bool:
    v = value.strip().strip("'").strip('"').strip()
    return v.lower() in DEFAULT_PASSWORDS


# --- INI ---------------------------------------------------------------

INI_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")
INI_KV = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.*?)\s*(?:[;#].*)?$")


def _scan_ini(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    section = ""
    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw.split(";", 1)[0].split("#", 1)[0]
        if not line.strip():
            continue
        m = INI_SECTION.match(line)
        if m:
            section = m.group(1).strip().lower()
            continue
        m = INI_KV.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if section == "security" and key == "admin_password":
            if _is_default(val):
                findings.append((i, f"grafana [security] admin_password={val!r} is a default credential"))
    return findings


# --- ENV / Dockerfile -------------------------------------------------

ENV_GF_PASS = re.compile(
    r"""(?ix)
    (?:^|[\s])
    (?:ENV\s+|ARG\s+|export\s+|-\s+|)?  # docker ENV/ARG, shell export, compose dash
    GF_SECURITY_ADMIN_PASSWORD
    \s*[=\s]\s*
    (['"]?)([^'"\s]+)\1
    """
)


def _scan_envish(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        # strip simple shell/dockerfile comments (but not in quoted strings;
        # cheap heuristic is fine for these surfaces)
        line = raw
        if "#" in line:
            # only strip when '#' is at the start or preceded by whitespace
            # so we don't truncate ENV X='abc#def'
            stripped = re.sub(r"(?:^|\s)#.*$", "", line)
            line = stripped
        m = ENV_GF_PASS.search(line)
        if not m:
            continue
        val = m.group(2)
        if _is_default(val):
            findings.append(
                (i, f"GF_SECURITY_ADMIN_PASSWORD={val!r} is a default credential")
            )
    return findings


# --- Helm / compose YAML ---------------------------------------------

YAML_KV = re.compile(
    r"""(?x)
    ^\s*
    (adminPassword|admin_password|GF_SECURITY_ADMIN_PASSWORD)
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
        if _is_default(val):
            findings.append(
                (i, f"grafana {key}: {val!r} is a default credential")
            )
    return findings


def _classify(path: Path, source: str) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name == "dockerfile" or suffix == ".dockerfile" or name.startswith("dockerfile."):
        return "envish"
    if suffix in (".ini", ".cfg", ".conf"):
        return "ini"
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if suffix in (".env", ".envfile", ".sh", ".bash", ".service"):
        return "envish"
    # Heuristic on contents.
    if "[security]" in source.lower():
        return "ini"
    if re.search(r"^\s*adminPassword\s*:", source, re.M):
        return "yaml"
    if "GF_SECURITY_ADMIN_PASSWORD" in source:
        return "envish"
    return "ini"


def scan(source: str, path: Path = Path("<stdin>")) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    kind = _classify(path, source)
    if kind == "ini":
        return _scan_ini(source)
    if kind == "yaml":
        # YAML files often also carry env-style entries (compose), so
        # check both shapes and merge by line.
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
                "grafana.ini", "custom.ini", "*.ini",
                "docker-compose*.yml", "docker-compose*.yaml",
                "values.yaml", "values.yml",
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
