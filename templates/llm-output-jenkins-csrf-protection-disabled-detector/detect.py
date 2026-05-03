#!/usr/bin/env python3
"""
llm-output-jenkins-csrf-protection-disabled-detector

Flags Jenkins controller configurations that disable the CSRF crumb
protection ("Prevent Cross Site Request Forgery exploits"). Jenkins
ships with this protection enabled since 2.222 / LTS 2.176; turning
it off makes every authenticated POST endpoint -- including
script-console, plugin install, build trigger -- vulnerable to
drive-by browser CSRF.

Disabling paths we flag:

  1. JCasC / config.xml:
       <crumbIssuer class="hudson.security.csrf.DefaultCrumbIssuer">
         ...
       </crumbIssuer>
     -- explicit removal: `<crumbIssuer class="..."/>` replaced by
     `<crumbIssuer class="none"/>` or `<crumbIssuer/>` removed
     entirely is hard to detect statically. We instead flag the
     positive disabling toggles:

  2. JVM system property:
       -Dhudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION=true
     (the documented Jenkins flag for disabling CSRF entirely).

  3. Groovy / Script Console one-liner that LLMs love:
       jenkins.model.Jenkins.instance.setCrumbIssuer(null)

  4. JCasC YAML:
       jenkins:
         crumbIssuer: null
     or
       jenkins:
         crumbIssuer: ~
     or absent crumbIssuer key with explicit `enableCSRF: false`
     (older controller-config plugin form).

  5. CLI / env that flips the same flag:
       JAVA_OPTS=... -Dhudson.security.csrf...DISABLE_CSRF_PROTECTION=true ...
       JENKINS_OPTS containing the same.

Maps to:
- CWE-352: Cross-Site Request Forgery (CSRF).
- OWASP A01:2021 Broken Access Control (CSRF subcategory).
- Jenkins Security Advisory: enabling CSRF protection is a baseline
  hardening step.

Stdlib-only. Reads files passed on argv (recurses into dirs and picks
*.xml, *.yml, *.yaml, *.groovy, *.gvy, Dockerfile*, docker-compose.*,
*.sh, *.bash, *.env.example, *.service).

Exit codes: 0 = no findings, 1 = findings, 2 = usage error.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List

# 1. JVM property that disables CSRF.
_JVM_FLAG = re.compile(
    r"""(?i)-Dhudson\.security\.csrf\.GlobalCrumbIssuerConfiguration\.DISABLE_CSRF_PROTECTION\s*=\s*true\b"""
)

# 2. Groovy form: setCrumbIssuer(null).
_GROOVY_NULL_CRUMB = re.compile(
    r"""\.setCrumbIssuer\s*\(\s*null\s*\)"""
)

# 3. JCasC YAML: crumbIssuer set to null / ~ / "none".
#    Match a YAML mapping line.
_YAML_CRUMB_NULL = re.compile(
    r"""(?im)^\s*crumbIssuer\s*:\s*(?:null|~|"null"|'null'|"none"|'none')\s*(?:#.*)?$"""
)

# 4. Older controller-config form: enableCSRF: false / "false".
_YAML_ENABLE_CSRF_FALSE = re.compile(
    r"""(?im)^\s*enableCSRF\s*:\s*(?:false|"false"|'false'|no|off|0)\b"""
)

# 5. Hudson XML config.xml form: <useCrumbs>false</useCrumbs> (older
#    Jenkins / Hudson lineage flag).
_XML_USE_CRUMBS_FALSE = re.compile(
    r"""(?i)<useCrumbs>\s*false\s*</useCrumbs>"""
)

# 6. Explicit XML crumbIssuer removal: <crumbIssuer class="none"/>
_XML_CRUMB_NONE = re.compile(
    r"""(?i)<crumbIssuer\b[^>]*class\s*=\s*["']none["'][^>]*/?>"""
)

_PATTERNS = [
    ("jvm-DISABLE_CSRF_PROTECTION-true", _JVM_FLAG),
    ("groovy-setCrumbIssuer-null", _GROOVY_NULL_CRUMB),
    ("jcasc-crumbIssuer-null", _YAML_CRUMB_NULL),
    ("config-enableCSRF-false", _YAML_ENABLE_CSRF_FALSE),
    ("xml-useCrumbs-false", _XML_USE_CRUMBS_FALSE),
    ("xml-crumbIssuer-class-none", _XML_CRUMB_NONE),
]

_COMMENT_LEADERS = ("#", "//", ";")

_INTERESTING_SUFFIXES = (
    ".xml", ".yml", ".yaml", ".groovy", ".gvy",
    ".sh", ".bash", ".env.example", ".service", ".conf",
)
_INTERESTING_NAMES = ("Dockerfile", "Jenkinsfile")


def _looks_interesting(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith("docker-compose"):
        return True
    for n in _INTERESTING_NAMES:
        if base == n or base.startswith(n + "."):
            return True
    for s in _INTERESTING_SUFFIXES:
        if base.endswith(s):
            return True
    return False


def _iter_files(args: Iterable[str]) -> Iterable[str]:
    for a in args:
        if os.path.isdir(a):
            for root, _dirs, files in os.walk(a):
                for f in files:
                    p = os.path.join(root, f)
                    if _looks_interesting(p):
                        yield p
        else:
            yield a


def _strip_line_comment(line: str) -> str:
    """Strip trailing #/// comment unless inside quotes. Preserve XML."""
    in_s = ""
    out = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_s:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(line[i + 1]); i += 2; continue
            if c == in_s:
                in_s = ""
            i += 1; continue
        if c in ("'", '"'):
            in_s = c; out.append(c); i += 1; continue
        if c == "#":
            break
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(c); i += 1
    return "".join(out)


def _is_pure_comment_line(raw: str, path: str) -> bool:
    stripped = raw.lstrip()
    if any(stripped.startswith(c) for c in _COMMENT_LEADERS):
        return True
    # XML/HTML one-line comment
    if stripped.startswith("<!--") and stripped.rstrip().endswith("-->"):
        return True
    return False


def scan_file(path: str) -> List[str]:
    findings: List[str] = []
    is_xml = path.lower().endswith(".xml")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                if _is_pure_comment_line(raw, path):
                    continue
                # XML files: do NOT strip on `#` (legitimate in attrs).
                line = raw if is_xml else _strip_line_comment(raw)
                for label, pat in _PATTERNS:
                    if pat.search(line):
                        findings.append(
                            f"{path}:{lineno}: {label}: {raw.rstrip()}"
                        )
                        break
    except OSError as e:
        print(f"{path}: read error: {e}", file=sys.stderr)
    return findings


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py <file-or-dir> [<file-or-dir> ...]",
            file=sys.stderr,
        )
        return 2
    any_hit = False
    for path in _iter_files(argv[1:]):
        for line in scan_file(path):
            print(line)
            any_hit = True
    return 1 if any_hit else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
