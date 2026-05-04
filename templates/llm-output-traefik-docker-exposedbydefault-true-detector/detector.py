#!/usr/bin/env python3
"""Detect Traefik configuration snippets emitted by LLMs that leave
the Docker provider's ``exposedByDefault`` flag set to ``true``.

Traefik's Docker / Swarm provider has an ``exposedByDefault`` knob.
When it is true, **every** container on the host is auto-routed by
Traefik unless individually opted out with
``traefik.enable=false``. The recommended (opt-in) posture is
``exposedByDefault=false`` and explicit ``traefik.enable=true``
labels per container that should be routed.

LLMs frequently emit one of these unsafe shapes when asked
"give me a traefik.yml" or "how do I deploy traefik with docker":

  1. Static-file YAML ``providers.docker.exposedByDefault: true``
     (the default in v2/v3 if the key is omitted is also ``true``,
     but explicit-true is what LLMs paste).
  2. TOML form ``[providers.docker]\\n  exposedByDefault = true``.
  3. CLI flag ``--providers.docker.exposedByDefault=true`` in a
     ``docker run traefik:...`` or compose ``command:`` block.
  4. Environment variable
     ``TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT=true``.

We also flag the common ``providers.docker:`` block that omits
``exposedByDefault`` AND does not add a ``defaultRule`` /
``constraints`` filter, since Traefik treats omission as ``true``.
That last rule is conservative: we only fire when ``providers.docker``
is configured AND no ``constraints`` / ``exposedByDefault: false`` /
``defaultRule`` is present anywhere in the file.

Suppression: a top-level ``# traefik-expose-all-ok`` comment in
the file disables all rules (intentional all-expose dev box).

Public API:
    detect(text: str) -> bool
    scan(text: str)   -> list[(line, reason)]

CLI:
    python3 detector.py <file> [<file> ...]
    Exit code = number of files with at least one finding.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SUPPRESS = "traefik-expose-all-ok"


def _strip_comments(text: str) -> str:
    """Strip ``#``-prefixed comments (full-line and inline) but preserve
    line numbering so reports line up with the source.
    """
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            nl = "\n" if line.endswith("\n") else ""
            out.append(nl)
            continue
        idx = -1
        in_quote = None
        for i, ch in enumerate(line):
            if in_quote:
                if ch == in_quote:
                    in_quote = None
                continue
            if ch in "\"'":
                in_quote = ch
                continue
            if ch == "#" and (i == 0 or line[i - 1].isspace()):
                idx = i
                break
        if idx >= 0:
            tail = "\n" if line.endswith("\n") else ""
            out.append(line[:idx].rstrip() + tail)
        else:
            out.append(line)
    return "".join(out)


_BOOL_TRUE = re.compile(r"""(?ix) ^ \s* (true|yes|on|1) \s* $ """)
_BOOL_FALSE = re.compile(r"""(?ix) ^ \s* (false|no|off|0) \s* $ """)


def _truthy(s: str) -> bool:
    return bool(_BOOL_TRUE.match(s))


def _falsy(s: str) -> bool:
    return bool(_BOOL_FALSE.match(s))


# YAML form: anywhere ``exposedByDefault: true`` (or yes/on/1) appears.
_YAML_EXPOSED_RE = re.compile(
    r"""(?im)
    ^\s*
    exposedByDefault
    \s*:\s*
    ["']?
    (?P<v>[A-Za-z0-9]+)
    ["']?
    """,
    re.VERBOSE,
)

# TOML form: ``exposedByDefault = true``.
_TOML_EXPOSED_RE = re.compile(
    r"""(?im)
    ^\s*
    exposedByDefault
    \s*=\s*
    (?P<v>[A-Za-z0-9]+)
    """,
    re.VERBOSE,
)

# CLI flag form: ``--providers.docker.exposedByDefault=true`` or
# ``--providers.docker.exposedByDefault true``.
_CLI_EXPOSED_RE = re.compile(
    r"""(?ix)
    --providers\.docker\.exposedByDefault
    \s*[= ]\s*
    ["']?
    (?P<v>[A-Za-z0-9]+)
    ["']?
    """,
)

# Env-var form: ``TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT=true``.
_ENV_EXPOSED_RE = re.compile(
    r"""(?ix)
    \b
    TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT
    \s*[=:]\s*
    ["']?
    (?P<v>[A-Za-z0-9]+)
    ["']?
    """,
)

# Detect that the file is configuring the Docker provider at all.
_DOCKER_BLOCK_YAML_RE = re.compile(
    r"""(?im) ^\s* docker \s* :""", re.VERBOSE
)
_DOCKER_BLOCK_TOML_RE = re.compile(
    r"""(?im) ^\s* \[\s* providers\.docker \s* \] """, re.VERBOSE
)
_PROVIDERS_BLOCK_YAML_RE = re.compile(
    r"""(?im) ^\s* providers \s* :""", re.VERBOSE
)

# Constraints / defaultRule presence (any form).
_CONSTRAINTS_RE = re.compile(
    r"""(?ix)
    (?:
        \b constraints \s* [:=]
        |
        --providers\.docker\.constraints
        |
        TRAEFIK_PROVIDERS_DOCKER_CONSTRAINTS
        |
        \b defaultRule \s* [:=]
        |
        --providers\.docker\.defaultRule
        |
        TRAEFIK_PROVIDERS_DOCKER_DEFAULTRULE
    )
    """,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan(text: str) -> list[tuple[int, str]]:
    if SUPPRESS in text:
        return []
    cleaned = _strip_comments(text)
    findings: list[tuple[int, str]] = []

    # Rule 1 + 2: explicit ``exposedByDefault: true`` (yaml or toml).
    seen_explicit_true = False
    seen_explicit_false = False
    for m in _YAML_EXPOSED_RE.finditer(cleaned):
        v = m.group("v")
        if _truthy(v):
            seen_explicit_true = True
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    "providers.docker.exposedByDefault: true - every container is routed unless opted out",
                )
            )
        elif _falsy(v):
            seen_explicit_false = True
    for m in _TOML_EXPOSED_RE.finditer(cleaned):
        v = m.group("v")
        if _truthy(v):
            seen_explicit_true = True
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    "providers.docker exposedByDefault = true (toml) - every container is routed unless opted out",
                )
            )
        elif _falsy(v):
            seen_explicit_false = True

    # Rule 3: CLI flag.
    for m in _CLI_EXPOSED_RE.finditer(cleaned):
        v = m.group("v")
        if _truthy(v):
            seen_explicit_true = True
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    "--providers.docker.exposedByDefault=true CLI flag - every container is routed unless opted out",
                )
            )
        elif _falsy(v):
            seen_explicit_false = True

    # Rule 4: env var.
    for m in _ENV_EXPOSED_RE.finditer(cleaned):
        v = m.group("v")
        if _truthy(v):
            seen_explicit_true = True
            findings.append(
                (
                    _line_of(cleaned, m.start()),
                    "TRAEFIK_PROVIDERS_DOCKER_EXPOSEDBYDEFAULT=true env var - every container is routed unless opted out",
                )
            )
        elif _falsy(v):
            seen_explicit_false = True

    # Rule 5 (conservative omission rule): file configures the docker
    # provider, but never sets exposedByDefault and never sets a
    # constraints / defaultRule filter. Only fire if no explicit value
    # was seen.
    docker_configured = bool(
        _DOCKER_BLOCK_TOML_RE.search(cleaned)
        or (
            _DOCKER_BLOCK_YAML_RE.search(cleaned)
            and _PROVIDERS_BLOCK_YAML_RE.search(cleaned)
        )
        or _CLI_EXPOSED_RE.search(cleaned)
        or re.search(r"--providers\.docker\b", cleaned)
        or re.search(r"\bTRAEFIK_PROVIDERS_DOCKER_\w+", cleaned)
    )
    if (
        docker_configured
        and not seen_explicit_true
        and not seen_explicit_false
        and not _CONSTRAINTS_RE.search(cleaned)
    ):
        # Anchor at the docker block declaration if we can find one.
        anchor = (
            _DOCKER_BLOCK_TOML_RE.search(cleaned)
            or _DOCKER_BLOCK_YAML_RE.search(cleaned)
        )
        ln = _line_of(cleaned, anchor.start()) if anchor else 1
        findings.append(
            (
                ln,
                "providers.docker configured without exposedByDefault: false and without constraints/defaultRule filter - default exposes every container",
            )
        )

    findings.sort(key=lambda t: t[0])
    return findings


def detect(text: str) -> bool:
    return bool(scan(text))


def _cli(argv: list[str]) -> int:
    if not argv:
        text = sys.stdin.read()
        hits = scan(text)
        for ln, reason in hits:
            print(f"<stdin>:{ln}: {reason}")
        return 1 if hits else 0

    files_with_hits = 0
    for arg in argv:
        p = Path(arg)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print(f"{arg}: cannot read: {e}", file=sys.stderr)
            files_with_hits += 1
            continue
        hits = scan(text)
        if hits:
            files_with_hits += 1
            for ln, reason in hits:
                print(f"{arg}:{ln}: {reason}")
    return files_with_hits


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
