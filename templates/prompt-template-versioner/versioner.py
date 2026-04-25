"""Named prompt template registry with semver-style version resolution
and explicit fallback chains.

Distinct from `prompt-version-pinning-manifest`:

- Manifest *pins* a single tuple by SHA-256 fingerprint and fails CI on
  drift. It is a lockfile.
- This versioner *resolves* a named template + version request to the
  best available concrete version and renders it. It is the registry
  that *produces* the artifact a manifest then pins.

Both compose: render via versioner, fingerprint with manifest, pin the
result.

Pure, stdlib-only. The registry is in-memory and intentionally tiny;
production deployments load it from a directory of files at startup
and never mutate at runtime.

Versions are `MAJOR.MINOR.PATCH` integers. The resolver supports four
specifiers:

- `"1.4.2"` — exact pin. Misses raise.
- `"1.4"`   — latest patch within MAJOR.MINOR. Misses raise.
- `"1"`     — latest minor.patch within MAJOR. Misses raise.
- `"latest"`— absolute latest registered version.

A `fallback_chain` lets a caller declare "I want 2.x; if nothing in 2.x
is registered, fall back to 1.x; never silently drop to 0.x." This is
the explicit alternative to letting `latest` drift across breaking
boundaries during a deploy.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass
from typing import Iterable


# --- version model ---------------------------------------------------------

Version = tuple[int, int, int]


def parse_version(s: str) -> Version:
    parts = s.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {s!r}")
    a, b, c = (int(p) for p in parts)
    return (a, b, c)


def format_version(v: Version) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


# --- registry --------------------------------------------------------------

@dataclass(frozen=True)
class Template:
    name: str
    version: Version
    body: str  # uses str.Template syntax: $var, ${var}


class TemplateNotFound(LookupError):
    pass


class TemplateRegistry:
    """In-memory map: (name, version) -> Template."""

    def __init__(self) -> None:
        self._by_name: dict[str, dict[Version, Template]] = {}

    def register(self, name: str, version: str, body: str) -> Template:
        v = parse_version(version)
        bucket = self._by_name.setdefault(name, {})
        if v in bucket:
            raise ValueError(f"already registered: {name} {format_version(v)}")
        t = Template(name=name, version=v, body=body)
        bucket[v] = t
        return t

    def all_versions(self, name: str) -> list[Version]:
        return sorted(self._by_name.get(name, {}).keys())

    def names(self) -> list[str]:
        return sorted(self._by_name.keys())


# --- resolver --------------------------------------------------------------

# Specifier syntax:
#   "MAJOR.MINOR.PATCH"  -- exact
#   "MAJOR.MINOR"        -- latest patch within minor
#   "MAJOR"              -- latest minor.patch within major
#   "latest"             -- absolute latest

_NUMERIC_RE = re.compile(r"^\d+(\.\d+){0,2}$")


def _matches(spec: str, v: Version) -> bool:
    if spec == "latest":
        return True
    parts = spec.split(".")
    nums = tuple(int(p) for p in parts)
    return v[: len(nums)] == nums


@dataclass
class Resolution:
    template: Template
    requested_spec: str
    matched_version: Version
    fell_back_from: list[str]  # earlier specs in the chain that found nothing

    def render(self, variables: dict[str, object]) -> str:
        # str.Template; missing variables raise KeyError loudly so a
        # template typo never silently emits an empty string.
        return string.Template(self.template.body).substitute(variables)


def resolve(
    registry: TemplateRegistry,
    name: str,
    spec: str,
) -> Template:
    if spec != "latest" and not _NUMERIC_RE.match(spec):
        raise ValueError(f"bad version spec: {spec!r}")
    versions = registry.all_versions(name)
    if not versions:
        raise TemplateNotFound(f"no template registered: {name!r}")
    matches = [v for v in versions if _matches(spec, v)]
    if not matches:
        raise TemplateNotFound(
            f"no version of {name!r} matches {spec!r} "
            f"(available: {[format_version(v) for v in versions]})"
        )
    chosen = max(matches)
    return registry._by_name[name][chosen]


def resolve_with_fallback(
    registry: TemplateRegistry,
    name: str,
    chain: Iterable[str],
) -> Resolution:
    """Try each spec in order; return the first that resolves.

    `chain` makes the fallback explicit and reviewable, instead of
    relying on `latest` and praying nothing registered a major bump.
    """
    chain_list = list(chain)
    if not chain_list:
        raise ValueError("fallback chain is empty")
    fell_back_from: list[str] = []
    for spec in chain_list:
        try:
            t = resolve(registry, name, spec)
            return Resolution(
                template=t,
                requested_spec=chain_list[0],
                matched_version=t.version,
                fell_back_from=fell_back_from,
            )
        except TemplateNotFound:
            fell_back_from.append(spec)
            continue
    raise TemplateNotFound(
        f"no version of {name!r} matched any spec in chain {chain_list!r}"
    )
