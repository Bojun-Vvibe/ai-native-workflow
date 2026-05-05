#!/usr/bin/env python3
"""Detect Caddy web-server configurations that disable automatic
HTTPS / certificate management across four common config surfaces:

* ``Caddyfile`` global option ``auto_https off``
* ``caddy.json`` adapter output (``automatic_https.disable: true``)
* ``docker-compose.yml`` env / command (``--auto-https off``,
  ``CADDY_AUTO_HTTPS=off``)
* ``Dockerfile`` ``CMD`` / ``ENTRYPOINT`` invocations

Suppression: a magic comment ``# caddy-auto-https-off-allowed``
silences the finding.

Stdlib-only. Exit code is the number of files with at least one
finding (capped at 255). Stdout lines: ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*caddy-auto-https-off-allowed")

OFF_LITERALS = {"off", "false", "0", "no", "disable", "disabled"}
TRUTHY = {"true", "1", "yes", "on"}


# --- Caddyfile --------------------------------------------------------

CADDYFILE_AUTO = re.compile(
    r"""(?ix)
    ^\s*
    auto_https
    \s+
    (off|disable|disabled|false|no|0)
    \s*(?:\#.*)?$
    """
)


def _scan_caddyfile(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        m = CADDYFILE_AUTO.match(raw)
        if not m:
            continue
        val = m.group(1).lower()
        if val in OFF_LITERALS:
            findings.append(
                (i, f"caddyfile auto_https {val} disables ACME / HTTP->HTTPS redirect")
            )
    return findings


# --- JSON (adapter output) -------------------------------------------

# Cheap line-oriented match; full JSON parsing would also work but the
# pattern is unambiguous enough that the line scanner is sufficient and
# matches the prior detector chain's style.
JSON_DISABLE = re.compile(
    r"""(?ix)
    "disable"\s*:\s*(true|1|"true"|"yes"|"on")
    """
)
JSON_AUTOMATIC_BLOCK = re.compile(r'"automatic_https"\s*:')


def _scan_json(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    lines = source.splitlines()
    # Find lines where "automatic_https": { appears, then look at the
    # next ~6 lines for "disable": true.
    for i, raw in enumerate(lines, start=1):
        if not JSON_AUTOMATIC_BLOCK.search(raw):
            continue
        window = lines[i - 1 : min(len(lines), i - 1 + 8)]
        for j, w in enumerate(window):
            if JSON_DISABLE.search(w):
                findings.append(
                    (
                        i + j,
                        "caddy json automatic_https.disable=true bypasses ACME / HTTP->HTTPS redirect",
                    )
                )
                break
    return findings


# --- ENV / Dockerfile / compose command ------------------------------

ENV_CADDY = re.compile(
    r"""(?ix)
    (?:^|[\s])
    (?:ENV\s+|ARG\s+|export\s+|-\s+)?
    CADDY_AUTO_HTTPS
    \s*[=\s]\s*
    (['"]?)([^'"\s]+)\1
    """
)

# CLI flag form: --auto-https off  (also -auto-https=off, with quotes,
# and Dockerfile JSON-array form `"--auto-https", "off"` where the
# separator between flag and value is `", "`).
CLI_FLAG = re.compile(
    r"""(?ix)
    --?auto-https
    (?:
        [\s=]+
        (['"]?)(off|disable|disabled|false|no|0)\1
        |
        ["']\s*,\s*["'](off|disable|disabled|false|no|0)["']
    )
    """
)


def _scan_envish(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        line = raw
        if "#" in line:
            line = re.sub(r"(?:^|\s)#.*$", "", line)

        m = ENV_CADDY.search(line)
        if m:
            val = m.group(2)
            if val.strip().lower() in OFF_LITERALS:
                findings.append(
                    (i, f"CADDY_AUTO_HTTPS={val!r} disables ACME / HTTP->HTTPS redirect")
                )

        m2 = CLI_FLAG.search(line)
        if m2:
            val = m2.group(2) or m2.group(3)
            findings.append(
                (i, f"caddy --auto-https {val} disables ACME / HTTP->HTTPS redirect")
            )

    # de-dup
    return sorted({(l, r) for l, r in findings})


def _classify(path: Path, source: str) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name == "caddyfile" or suffix == ".caddyfile":
        return "caddyfile"
    if suffix == ".json":
        return "json"
    if name == "dockerfile" or suffix == ".dockerfile" or name.startswith("dockerfile."):
        return "envish"
    if suffix in (".yaml", ".yml"):
        # compose with command/env; no native auto_https key in YAML.
        return "envish"
    if suffix in (".envfile", ".sh", ".bash", ".service", ".conf"):
        return "envish"
    # Heuristic on contents.
    if re.search(r"^\s*auto_https\s+", source, re.M):
        return "caddyfile"
    if '"automatic_https"' in source:
        return "json"
    if "CADDY_AUTO_HTTPS" in source or "--auto-https" in source:
        return "envish"
    return "caddyfile"


def scan(source: str, path: Path = Path("<stdin>")) -> List[Tuple[int, str]]:
    if SUPPRESS.search(source):
        return []
    kind = _classify(path, source)
    if kind == "caddyfile":
        return _scan_caddyfile(source)
    if kind == "json":
        return _scan_json(source)
    return _scan_envish(source)


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for pat in (
                "Caddyfile", "*.Caddyfile", "*.caddyfile",
                "caddy.json", "*.json",
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
