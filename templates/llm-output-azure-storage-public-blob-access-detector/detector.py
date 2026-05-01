#!/usr/bin/env python3
"""Detect Terraform configurations that make Azure storage blobs publicly
readable without authentication.

Azure Storage exposes two distinct public-access knobs that are easy for
LLMs to mis-set:

  1. **Account-level**: ``azurerm_storage_account.allow_nested_items_to_be_public``
     (formerly ``allow_blob_public_access``). When ``true``, any container
     in the account *may* opt into anonymous access. When ``false``, no
     container can be public regardless of its own setting. Setting it to
     ``true`` removes a defense-in-depth ceiling.

  2. **Container-level**: ``azurerm_storage_container.container_access_type``.
     - ``"private"`` (default) — auth required.
     - ``"blob"``  — anonymous read of individual blobs.
     - ``"container"`` — anonymous list + read of every blob.

  3. Network bypass: ``azurerm_storage_account_network_rules.default_action = "Allow"``
     opens the storage account to every IP on the public Internet (the
     opposite of the intended ``"Deny"`` allowlist posture).

LLM-generated Terraform routinely emits any of:

    resource "azurerm_storage_account" "x" {
      allow_nested_items_to_be_public = true
    }
    resource "azurerm_storage_container" "x" {
      container_access_type = "container"
    }
    resource "azurerm_storage_account_network_rules" "x" {
      default_action = "Allow"
    }

This detector flags those settings in ``.tf`` and ``.tf.json`` files.

CWE refs:
  - CWE-732: Incorrect Permission Assignment for Critical Resource
  - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
  - CWE-284: Improper Access Control

False-positive surface:
  - Public website / static-site hosting containers that *are* meant to
    be world-readable (``$web``, ``public-assets``). Suppress per line
    with a trailing ``# storage-public-allowed`` comment.

Usage:
    python3 detector.py <path> [<path> ...]

Exit code: number of files with at least one finding (capped at 255).
Stdout:    ``<file>:<line>:<reason>``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

SUPPRESS = re.compile(r"#\s*storage-public-allowed")

PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\ballow_nested_items_to_be_public\s*=\s*true\b",
            re.IGNORECASE,
        ),
        "allow_nested_items_to_be_public=true permits any container to go anonymous",
    ),
    (
        re.compile(
            r"\ballow_blob_public_access\s*=\s*true\b",
            re.IGNORECASE,
        ),
        "allow_blob_public_access=true permits any container to go anonymous",
    ),
    (
        re.compile(
            r"\bcontainer_access_type\s*=\s*\"(?:blob|container)\"",
            re.IGNORECASE,
        ),
        "container_access_type=blob/container exposes blobs to anonymous reads",
    ),
    (
        re.compile(
            r"\bdefault_action\s*=\s*\"Allow\"",
        ),
        "storage network rules default_action=Allow opens the account to the public Internet",
    ),
    (
        re.compile(
            r"\bpublic_network_access_enabled\s*=\s*true\b",
            re.IGNORECASE,
        ),
        "public_network_access_enabled=true exposes the storage account control-plane",
    ),
    (
        re.compile(
            r"\bshared_access_key_enabled\s*=\s*true\b.*#\s*default",
            re.IGNORECASE,
        ),
        "shared_access_key_enabled=true keeps long-lived keys usable",
    ),
]


def scan_source(source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    seen: set[Tuple[int, str]] = set()
    for i, line in enumerate(source.splitlines(), start=1):
        if SUPPRESS.search(line):
            continue
        # Strip trailing HCL comments (// or # not inside strings).
        # Cheap heuristic: split on " //" and " #" outside quotes.
        code = line
        # Remove suppression annotations isn't the only reason to keep #;
        # we want to ignore any other inline #/// comment when matching.
        # Use a conservative split: drop everything after the first " #"
        # (space-hash) or "//" — patterns we care about don't contain those.
        for sep in (" #", "//"):
            idx = code.find(sep)
            if idx >= 0:
                code = code[:idx]
        for pat, reason in PATTERNS:
            if pat.search(code):
                key = (i, reason)
                if key not in seen:
                    seen.add(key)
                    findings.append(key)
                break
    return findings


def scan_paths(paths: Iterable[Path]) -> int:
    bad_files = 0
    targets: List[Path] = []
    for path in paths:
        if path.is_dir():
            for ext in ("*.tf", "*.tf.json", "*.tfvars"):
                targets.extend(sorted(path.rglob(ext)))
        else:
            targets.append(path)
    for f in targets:
        try:
            source = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{f}:0:read-error: {exc}")
            continue
        hits = scan_source(source)
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
