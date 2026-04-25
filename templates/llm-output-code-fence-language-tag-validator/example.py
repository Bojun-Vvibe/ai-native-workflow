"""llm-output-code-fence-language-tag-validator — pure stdlib.

Scans Markdown prose for fenced code blocks (lines starting with three
or more backticks) and validates the language tag on the opening fence.

The bug class this template catches is the silent-corruption case
where an LLM emits a fenced code block but forgets the language tag,
or uses an inconsistent tag style across the same document, or uses
a tag that does not match the actual content (a `python` tag on what
is obviously a JSON object). Renderers happily display the block
either way; downstream syntax-highlighters, doc-search indexers, and
"copy as code" UI affordances all degrade silently.

One forward scan, no regex. The state machine is a 1-bit "inside a
fence?" flag plus the opening fence's column / fence-char / fence-len
so a closer must match (CommonMark fence-pairing rule).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Set


class FenceValidationError(ValueError):
    """Raised eagerly on bad input (non-str prose)."""


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int  # 1-indexed; opening-fence line for fence-level findings
    detail: str


@dataclass
class Result:
    fences: int
    tags_seen: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    ok: bool = True


# Lightweight content-vs-tag heuristics. Conservative — only fires
# when the body has a strong, unambiguous signal.
def _looks_like_json(body: str) -> bool:
    s = body.strip()
    if not s:
        return False
    if not (s[0] in "{[" and s[-1] in "}]"):
        return False
    # at least one quoted-key colon pair to reduce false positives
    return ('":' in s) or ("': " in s)


def _looks_like_shell(body: str) -> bool:
    for ln in body.splitlines():
        s = ln.lstrip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("$ ") or s.startswith("# "):
            return True
        head = s.split(None, 1)[0] if s else ""
        if head in {
            "cd",
            "ls",
            "rm",
            "mv",
            "cp",
            "mkdir",
            "echo",
            "cat",
            "grep",
            "sed",
            "awk",
            "git",
            "curl",
            "wget",
            "python3",
            "pip",
            "npm",
            "yarn",
            "make",
            "docker",
            "kubectl",
            "ssh",
            "tar",
            "find",
        }:
            return True
        return False
    return False


def _looks_like_python(body: str) -> bool:
    for ln in body.splitlines():
        s = ln.lstrip()
        if not s or s.startswith("#"):
            continue
        if (
            s.startswith("def ")
            or s.startswith("class ")
            or s.startswith("import ")
            or s.startswith("from ")
            or s.startswith("print(")
        ):
            return True
        return False
    return False


def validate(
    prose: str,
    *,
    require_language_tag: bool = True,
    allowed_tags: Optional[Set[str]] = None,
) -> Result:
    if not isinstance(prose, str):
        raise FenceValidationError("prose must be str")

    findings: List[Finding] = []
    tags_seen: List[str] = []
    fences = 0

    lines = prose.split("\n")
    in_fence = False
    open_line = 0
    open_char = ""
    open_len = 0
    open_indent = 0
    open_tag = ""
    body_lines: List[str] = []

    for li, raw in enumerate(lines, start=1):
        # measure leading whitespace
        i = 0
        while i < len(raw) and raw[i] == " ":
            i += 1
        rest = raw[i:]
        # detect a fence line: 3+ of '`' or '~' at the start of `rest`
        fence_char = ""
        if rest.startswith("```"):
            fence_char = "`"
        elif rest.startswith("~~~"):
            fence_char = "~"

        if fence_char:
            j = 0
            while j < len(rest) and rest[j] == fence_char:
                j += 1
            run_len = j
            after = rest[j:]
            tag_part = after.strip()

            if not in_fence:
                in_fence = True
                fences += 1
                open_line = li
                open_char = fence_char
                open_len = run_len
                open_indent = i
                open_tag = tag_part
                body_lines = []

                if not tag_part:
                    if require_language_tag:
                        findings.append(
                            Finding(
                                kind="missing_language_tag",
                                line=li,
                                detail="opening fence has no language tag",
                            )
                        )
                else:
                    tags_seen.append(tag_part)
                    if " " in tag_part:
                        findings.append(
                            Finding(
                                kind="suspicious_tag_whitespace",
                                line=li,
                                detail=f"tag contains whitespace: '{tag_part}'",
                            )
                        )
                    elif tag_part != tag_part.lower():
                        findings.append(
                            Finding(
                                kind="non_lowercase_tag",
                                line=li,
                                detail=(
                                    f"tag '{tag_part}' is not lowercase "
                                    f"(prefer '{tag_part.lower()}')"
                                ),
                            )
                        )
                    if allowed_tags is not None and tag_part.lower() not in allowed_tags:
                        findings.append(
                            Finding(
                                kind="unknown_tag",
                                line=li,
                                detail=(
                                    f"tag '{tag_part}' not in allowed set "
                                    f"{sorted(allowed_tags)}"
                                ),
                            )
                        )
                continue
            else:
                # closing-fence candidate: must be same char, len >= open_len,
                # same indent, and have an EMPTY tag-part (CommonMark rule).
                if (
                    fence_char == open_char
                    and run_len >= open_len
                    and i == open_indent
                    and tag_part == ""
                ):
                    body = "\n".join(body_lines)
                    # content-mismatch checks (only when a tag was given)
                    tag_low = open_tag.lower()
                    if tag_low in {"py", "python", "python3"}:
                        if _looks_like_json(body) and not _looks_like_python(body):
                            findings.append(
                                Finding(
                                    kind="tag_content_mismatch",
                                    line=open_line,
                                    detail=(
                                        f"tag '{open_tag}' but body parses as JSON"
                                    ),
                                )
                            )
                    elif tag_low == "json":
                        if not _looks_like_json(body):
                            findings.append(
                                Finding(
                                    kind="tag_content_mismatch",
                                    line=open_line,
                                    detail=(
                                        f"tag '{open_tag}' but body is not JSON-shaped"
                                    ),
                                )
                            )
                    elif tag_low in {"sh", "bash", "shell", "zsh"}:
                        if not _looks_like_shell(body) and (
                            _looks_like_python(body) or _looks_like_json(body)
                        ):
                            findings.append(
                                Finding(
                                    kind="tag_content_mismatch",
                                    line=open_line,
                                    detail=(
                                        f"tag '{open_tag}' but body looks like "
                                        f"{'python' if _looks_like_python(body) else 'JSON'}"
                                    ),
                                )
                            )
                    in_fence = False
                    body_lines = []
                    continue
                # otherwise: it's a backtick line *inside* the fenced block
                body_lines.append(raw)
                continue

        if in_fence:
            body_lines.append(raw)

    if in_fence:
        findings.append(
            Finding(
                kind="unclosed_fence",
                line=open_line,
                detail=(
                    f"opening fence at line {open_line} never closed "
                    f"(char='{open_char}', len={open_len})"
                ),
            )
        )

    # cross-fence: mixed tag style for the same logical language
    norm = {}
    for t in tags_seen:
        low = t.lower()
        canon = {"py": "python", "python3": "python", "shell": "bash", "sh": "bash", "zsh": "bash"}.get(low, low)
        norm.setdefault(canon, set()).add(low)
    for canon, variants in sorted(norm.items()):
        if len(variants) > 1:
            findings.append(
                Finding(
                    kind="inconsistent_tag_style",
                    line=0,
                    detail=(
                        f"language '{canon}' tagged as {sorted(variants)} "
                        f"in the same document"
                    ),
                )
            )

    findings.sort(key=lambda f: (f.kind, f.line, f.detail))
    return Result(
        fences=fences,
        tags_seen=tags_seen,
        findings=findings,
        ok=(not findings),
    )


# ---------- worked example ----------

_CASES = [
    (
        "01_clean_python",
        "Here is a snippet:\n```python\ndef add(a, b):\n    return a + b\n```\n",
        {},
    ),
    (
        "02_missing_tag",
        "Untagged block:\n```\nprint('hi')\n```\n",
        {},
    ),
    (
        "03_inconsistent_tag_style",
        "First:\n```py\nx = 1\n```\n\nSecond:\n```python\ny = 2\n```\n",
        {},
    ),
    (
        "04_tag_content_mismatch_python_is_json",
        "Mismatch:\n```python\n{\"name\": \"alice\", \"age\": 30}\n```\n",
        {},
    ),
    (
        "05_unclosed_fence",
        "Open and never closed:\n```bash\necho hello\n",
        {},
    ),
    (
        "06_unknown_tag_with_allowlist",
        "Custom DSL:\n```myql\nSELECT 1;\n```\n",
        {"allowed_tags": {"python", "bash", "json", "sql"}},
    ),
    (
        "07_non_lowercase_tag",
        "Caps:\n```Python\nprint(1)\n```\n",
        {},
    ),
    (
        "08_tilde_fence_with_inner_backticks",
        "Tilde-fenced block that contains a triple-backtick line in the body:\n~~~markdown\nUse ``` to start a code fence.\n~~~\n",
        {},
    ),
]


def _main():
    print("# llm-output-code-fence-language-tag-validator — worked example")
    print()
    for name, prose, kwargs in _CASES:
        print(f"## case {name}")
        print(f"kwargs: {json.dumps({k: sorted(v) if isinstance(v, set) else v for k, v in kwargs.items()}, sort_keys=True)}")
        print("prose:")
        for ln in prose.rstrip("\n").split("\n"):
            print(f"  | {ln}")
        try:
            r = validate(prose, **kwargs)
            payload = {
                "fences": r.fences,
                "findings": [asdict(f) for f in r.findings],
                "ok": r.ok,
                "tags_seen": r.tags_seen,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        except FenceValidationError as e:
            print(f"ERROR: {e}")
        print()


if __name__ == "__main__":
    _main()
