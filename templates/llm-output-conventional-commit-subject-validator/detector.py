"""llm-output-conventional-commit-subject-validator — checker + worked demo.

Pure-stdlib validator for Conventional Commits 1.0.0 *subject lines*
embedded in markdown emitted by an LLM. When an agent proposes a
commit message inside a fenced shell / git block (e.g.
``` ```bash\\ngit commit -m "..."\\n``` ``` or ``` ```git\\nfeat: ...\\n``` ```),
the subject is the contract the downstream merge-queue / changelog
generator will read. A subject that drifts from the spec breaks
release-please, semantic-release, conventional-changelog, and most
in-house bump scripts — silently, by miscategorising the change.

This validator extracts subject candidates from markdown fenced code
blocks tagged as one of: bash, sh, shell, zsh, console, git,
gitcommit, commit. It pulls the subject from:

  * the argument of `git commit -m "<subject>"` (single OR double
    quoted) — `-m '...'` is also recognised
  * the first non-empty, non-comment line of a `git` / `gitcommit` /
    `commit` block (the canonical commit-message file shape)

It then runs the subject through Conventional Commits 1.0.0 rules
and reports specific, actionable findings.

What it catches per subject:

  * missing_type            — no type prefix at all
  * unknown_type            — type is not in the allowed set
                              (feat, fix, docs, style, refactor,
                              perf, test, build, ci, chore, revert)
  * empty_scope             — `feat(): ...` (parens with nothing in)
  * scope_whitespace        — scope contains spaces or tabs
  * missing_colon_space     — colon is not followed by exactly one space
                              before the description
  * empty_description       — nothing after the colon-space
  * trailing_period         — description ends with `.`
  * subject_too_long        — subject exceeds 72 characters (the
                              widely-followed soft cap; configurable)
  * leading_capital         — description starts with an uppercase
                              letter (most projects mandate lowercase)
  * breaking_marker_misplaced — `!` appears somewhere other than
                              right before the colon

Design notes:

  * Code-fence-aware. Only inspects content inside fenced blocks
    whose info-string first token (case-insensitive) is one of the
    recognised tags. Everything else is ignored.
  * `-m` extraction is quote-aware (single AND double, with escape
    handling for `\\"` and `\\'`). Multiple `-m` flags = multiple
    subjects.
  * For `git` / `gitcommit` / `commit` blocks we also pull the first
    non-empty, non-comment line as a subject.
  * Pure function. `detect(src) -> CommitSubjectReport`. No I/O,
    no clocks, no transport.
  * Stdlib only. dataclasses + json + sys.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple


ALLOWED_TYPES = frozenset({
    "feat", "fix", "docs", "style", "refactor", "perf",
    "test", "build", "ci", "chore", "revert",
})

SHELL_FENCES = frozenset({"bash", "sh", "shell", "zsh", "console"})
GIT_FENCES = frozenset({"git", "gitcommit", "commit"})

DEFAULT_MAX_SUBJECT_LEN = 72


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int        # 1-indexed line of the subject in the original src
    subject: str        # the subject text we evaluated
    detail: str


@dataclass
class CommitSubjectReport:
    ok: bool
    subjects_checked: int
    fences_inspected: int
    findings: List[Finding] = field(default_factory=list)


def _fence_open_tag(line: str) -> Optional[str]:
    s = line.lstrip()
    if not (s.startswith("```") or s.startswith("~~~")):
        return None
    info = s[3:].strip()
    if not info:
        return ""
    return info.split()[0].lower().strip(",")


def _is_fence_close(line: str) -> bool:
    return line.strip() in ("```", "~~~")


def _scan_quoted(s: str, start: int) -> Tuple[Optional[str], int]:
    """Scan a quoted string starting at s[start] in {'"', "'"}.
    Return (value, end_index_exclusive). Returns (None, start) on
    unterminated quote."""
    quote = s[start]
    out: List[str] = []
    j = start + 1
    while j < len(s):
        c = s[j]
        if c == "\\" and j + 1 < len(s):
            nxt = s[j + 1]
            if nxt == quote or nxt == "\\":
                out.append(nxt)
                j += 2
                continue
            out.append(c)
            j += 1
            continue
        if c == quote:
            return "".join(out), j + 1
        out.append(c)
        j += 1
    return None, start


def _extract_dash_m_subjects(line: str) -> List[str]:
    """Find all `-m "..."` / `-m '...'` / `--message="..."` subjects on a
    single line. Returns the subject strings in order."""
    subjects: List[str] = []
    i = 0
    n = len(line)
    while i < n:
        # match `-m` or `--message`
        matched = False
        if line[i:i + 2] == "-m" and (i + 2 >= n or line[i + 2] in (" ", "\t", "=")):
            j = i + 2
            matched = True
        elif line[i:i + 9] == "--message" and (i + 9 >= n or line[i + 9] in (" ", "\t", "=")):
            j = i + 9
            matched = True
        if matched:
            # skip = or whitespace
            while j < n and line[j] in (" ", "\t", "="):
                j += 1
            if j < n and line[j] in ('"', "'"):
                val, end = _scan_quoted(line, j)
                if val is not None:
                    subjects.append(val.split("\n", 1)[0])
                    i = end
                    continue
            # bare token (rare): take to next whitespace
            if j < n:
                k = j
                while k < n and line[k] not in (" ", "\t"):
                    k += 1
                subjects.append(line[j:k])
                i = k
                continue
        i += 1
    return subjects


def _validate_subject(subject: str, max_len: int) -> List[Tuple[str, str]]:
    """Return list of (kind, detail) findings for one subject."""
    out: List[Tuple[str, str]] = []
    if not subject:
        out.append(("empty_description", "subject is empty"))
        return out

    if len(subject) > max_len:
        out.append((
            "subject_too_long",
            f"subject is {len(subject)} chars, exceeds soft cap of {max_len}",
        ))

    # Find the first ':'. Per spec: <type>[(scope)][!]: <description>
    colon_idx = subject.find(":")
    if colon_idx < 0:
        out.append(("missing_type", "no ':' found; cannot parse a type prefix"))
        return out

    prefix = subject[:colon_idx]
    after = subject[colon_idx + 1:]

    # parse prefix: type, optional (scope), optional !
    bang = False
    scope: Optional[str] = None
    type_str = prefix

    if prefix.endswith("!"):
        bang = True
        type_str = prefix[:-1]

    # scope?
    if "(" in type_str and type_str.endswith(")"):
        lp = type_str.index("(")
        scope = type_str[lp + 1:-1]
        type_str = type_str[:lp]

    # bang misplaced?
    if "!" in type_str:
        out.append((
            "breaking_marker_misplaced",
            "`!` must appear immediately before the `:`",
        ))
        type_str = type_str.replace("!", "")

    if not type_str:
        out.append(("missing_type", "type token before ':' is empty"))
    elif type_str not in ALLOWED_TYPES:
        out.append((
            "unknown_type",
            f"type `{type_str}` is not in the allowed set "
            f"({', '.join(sorted(ALLOWED_TYPES))})",
        ))

    if scope is not None:
        if scope == "":
            out.append(("empty_scope", "`()` is present but contains no scope"))
        elif any(ch in scope for ch in (" ", "\t")):
            out.append((
                "scope_whitespace",
                f"scope `{scope}` contains whitespace",
            ))

    # colon-space rule: exactly one space between ':' and description
    if not after.startswith(" "):
        out.append((
            "missing_colon_space",
            "colon must be followed by exactly one space before the description",
        ))
        description = after.lstrip()
    elif after.startswith("  "):
        out.append((
            "missing_colon_space",
            "colon followed by more than one space before the description",
        ))
        description = after.lstrip()
    else:
        description = after[1:]

    if not description.strip():
        out.append(("empty_description", "description after `: ` is empty"))
        return out

    if description.endswith("."):
        out.append((
            "trailing_period",
            "description ends with `.`; convention is to omit terminal punctuation",
        ))

    if description[0:1].isalpha() and description[0:1] == description[0:1].upper():
        out.append((
            "leading_capital",
            f"description starts with uppercase `{description[0]}`; "
            "convention is lowercase",
        ))

    return out


def detect(src: str, max_len: int = DEFAULT_MAX_SUBJECT_LEN) -> CommitSubjectReport:
    findings: List[Finding] = []
    fences_inspected = 0
    subjects_checked = 0

    lines = src.splitlines()
    in_fence = False
    fence_tag: Optional[str] = None
    fence_start_line = 0

    for idx, line in enumerate(lines, start=1):
        if not in_fence:
            tag = _fence_open_tag(line)
            if tag is not None and (tag in SHELL_FENCES or tag in GIT_FENCES):
                in_fence = True
                fence_tag = tag
                fence_start_line = idx
            continue

        if _is_fence_close(line):
            in_fence = False
            fence_tag = None
            continue

        fence_inspect_increment = False

        # shell-style: scan the line for `git commit -m`
        if fence_tag in SHELL_FENCES:
            # only consider lines that mention `git commit`
            if "git commit" in line or "git  commit" in line:
                subs = _extract_dash_m_subjects(line)
                for sub in subs:
                    subjects_checked += 1
                    fence_inspect_increment = True
                    for kind, detail in _validate_subject(sub, max_len):
                        findings.append(Finding(
                            kind=kind,
                            line_no=idx,
                            subject=sub,
                            detail=detail,
                        ))

        # git-style: first non-empty non-comment line of the block
        elif fence_tag in GIT_FENCES:
            if idx == fence_start_line + 1 or _is_first_payload_line(
                lines, fence_start_line, idx
            ):
                stripped = line.rstrip()
                if stripped and not stripped.lstrip().startswith("#"):
                    subjects_checked += 1
                    fence_inspect_increment = True
                    for kind, detail in _validate_subject(stripped, max_len):
                        findings.append(Finding(
                            kind=kind,
                            line_no=idx,
                            subject=stripped,
                            detail=detail,
                        ))

        if fence_inspect_increment:
            fences_inspected += 1

    findings.sort(key=lambda f: (f.line_no, f.kind, f.subject))
    return CommitSubjectReport(
        ok=len(findings) == 0,
        subjects_checked=subjects_checked,
        fences_inspected=len(set(_subject_line_to_fence(findings)))
                           if findings else fences_inspected,
        findings=findings,
    )


def _is_first_payload_line(lines: List[str], fence_start_line: int, idx: int) -> bool:
    """For git-tagged blocks: return True if `idx` is the first
    non-empty / non-comment line after the fence open."""
    for j in range(fence_start_line + 1, idx):
        candidate = lines[j - 1]
        if candidate.strip() == "":
            continue
        if candidate.lstrip().startswith("#"):
            continue
        return False
    candidate = lines[idx - 1]
    if candidate.strip() == "":
        return False
    if candidate.lstrip().startswith("#"):
        return False
    return True


def _subject_line_to_fence(findings: List[Finding]) -> List[int]:
    return [f.line_no for f in findings]


def report_to_json(rep: CommitSubjectReport) -> str:
    return json.dumps(
        {
            "ok": rep.ok,
            "subjects_checked": rep.subjects_checked,
            "fences_inspected": rep.fences_inspected,
            "findings": [asdict(f) for f in rep.findings],
        },
        indent=2,
        sort_keys=True,
    )


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detector.py <markdown-file> [<markdown-file> ...]",
            file=sys.stderr,
        )
        return 2
    overall_ok = True
    for path in argv[1:]:
        rep = detect(_read(path))
        print(f"=== {path} ===")
        print(report_to_json(rep))
        if not rep.ok:
            overall_ok = False
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
