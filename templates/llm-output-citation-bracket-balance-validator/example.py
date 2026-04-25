"""llm-output-citation-bracket-balance-validator

Pure stdlib validator for inline numeric citation brackets in LLM
prose: `[1]`, `[2]`, `[1, 3]`, `[1-3]`. Catches the silent-corruption
class where the model drops a closing bracket, opens a citation it
never closes, references an id higher than the bibliography contains,
or skips an id (`[1] ... [3]` with no `[2]` anywhere — usually means
the model "forgot" to insert a sentence that cited source 2).

Findings are independent of any specific bibliography format; the
caller passes `max_id` (size of the references list) and the template
checks that every cited id is in `[1, max_id]`.

No regex. Single forward pass over the string. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


class CitationValidationError(ValueError):
    """Raised eagerly on malformed input (non-string prose)."""


@dataclass(frozen=True)
class Finding:
    kind: str          # one of: unclosed_bracket, stray_close, empty_citation,
                       # non_numeric, out_of_range, skipped_id, descending_range,
                       # duplicate_in_same_bracket
    detail: str
    pos: int           # character offset into the prose


@dataclass
class ValidationResult:
    ok: bool
    cited_ids: List[int] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "cited_ids": self.cited_ids,
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def _parse_bracket_body(body: str, start_pos: int) -> Tuple[List[int], List[Finding]]:
    """Parse the inside of a `[...]`. Returns (ids, findings)."""
    findings: List[Finding] = []
    ids: List[int] = []
    seen_in_this_bracket: set = set()
    body_stripped = body.strip()
    if not body_stripped:
        findings.append(Finding("empty_citation", "[] with no content", start_pos))
        return ids, findings
    # split on commas
    for chunk in body_stripped.split(","):
        chunk = chunk.strip()
        if not chunk:
            findings.append(
                Finding("empty_citation", f"empty entry in bracket: {body!r}", start_pos)
            )
            continue
        if "-" in chunk:
            # range form like "1-3"
            parts = chunk.split("-")
            if len(parts) != 2 or not parts[0].strip().isdigit() or not parts[1].strip().isdigit():
                findings.append(
                    Finding("non_numeric", f"non-numeric range entry: {chunk!r}", start_pos)
                )
                continue
            lo, hi = int(parts[0].strip()), int(parts[1].strip())
            if hi < lo:
                findings.append(
                    Finding(
                        "descending_range",
                        f"range goes backwards: {chunk!r}",
                        start_pos,
                    )
                )
                continue
            for n in range(lo, hi + 1):
                if n in seen_in_this_bracket:
                    findings.append(
                        Finding(
                            "duplicate_in_same_bracket",
                            f"id {n} appears twice in the same bracket {body!r}",
                            start_pos,
                        )
                    )
                else:
                    seen_in_this_bracket.add(n)
                    ids.append(n)
        else:
            if not chunk.isdigit():
                findings.append(
                    Finding("non_numeric", f"non-numeric entry: {chunk!r}", start_pos)
                )
                continue
            n = int(chunk)
            if n in seen_in_this_bracket:
                findings.append(
                    Finding(
                        "duplicate_in_same_bracket",
                        f"id {n} appears twice in the same bracket {body!r}",
                        start_pos,
                    )
                )
            else:
                seen_in_this_bracket.add(n)
                ids.append(n)
    return ids, findings


def validate(
    prose: str,
    *,
    max_id: Optional[int] = None,
    require_dense_sequence: bool = True,
) -> ValidationResult:
    """Validate inline citation brackets in `prose`.

    Args:
        prose: the LLM output text.
        max_id: optional upper bound on legal citation ids (size of
            the bibliography). Citations above this fire `out_of_range`.
        require_dense_sequence: if True (default), and the prose cites
            ids `{1, 3, 5}`, fire `skipped_id` for 2 and 4. The premise
            is that a well-formed document with N references uses ids
            1..N contiguously. Set False for documents that legitimately
            omit some sources.

    Returns:
        ValidationResult with `ok=False` iff any finding fired.
    """
    if not isinstance(prose, str):
        raise CitationValidationError(f"prose must be str, got {type(prose).__name__}")

    findings: List[Finding] = []
    cited: List[int] = []
    cited_set: set = set()

    i = 0
    n = len(prose)
    while i < n:
        ch = prose[i]
        if ch == "[":
            # find matching ']'
            j = prose.find("]", i + 1)
            if j == -1:
                findings.append(
                    Finding("unclosed_bracket", "'[' with no matching ']'", i)
                )
                break  # rest of prose is suspect; stop scanning brackets
            body = prose[i + 1 : j]
            # Treat as a citation attempt if the body contains any
            # digit. Pure-text brackets like "[citation needed]" or
            # "[TODO]" have no digits and are passed through as
            # ordinary prose. A bracket like "[1, two]" still parses
            # as a citation attempt because the digit signals intent;
            # the literal "two" then fires `non_numeric`.
            if any(c.isdigit() for c in body):
                ids, sub = _parse_bracket_body(body, i)
                findings.extend(sub)
                for nid in ids:
                    if max_id is not None and (nid < 1 or nid > max_id):
                        findings.append(
                            Finding(
                                "out_of_range",
                                f"citation [{nid}] outside [1, {max_id}]",
                                i,
                            )
                        )
                    if nid not in cited_set:
                        cited_set.add(nid)
                        cited.append(nid)
            i = j + 1
        elif ch == "]":
            findings.append(Finding("stray_close", "']' with no matching '['", i))
            i += 1
        else:
            i += 1

    if require_dense_sequence and cited_set:
        full = set(range(1, max(cited_set) + 1))
        gaps = sorted(full - cited_set)
        for g in gaps:
            findings.append(
                Finding(
                    "skipped_id",
                    f"id {g} never cited (cited up to {max(cited_set)})",
                    -1,
                )
            )

    # Stable order: by (kind, pos, detail)
    findings.sort(key=lambda f: (f.kind, f.pos, f.detail))
    cited.sort()

    return ValidationResult(ok=not findings, cited_ids=cited, findings=findings)


# ---------------------------------------------------------------------------
# Worked example
# ---------------------------------------------------------------------------

_CASES = [
    (
        "01_clean",
        "Recent work [1] confirms the trend. Earlier surveys [2, 3] disagree, and a meta-analysis [1-3] reconciles them.",
        3,
        True,
    ),
    (
        "02_unclosed_bracket",
        "The reviewer cites [1, 2 and walks away mid-sentence.",
        5,
        True,
    ),
    (
        "03_skipped_id",
        "First, see [1]. Then jump straight to [3] without ever citing source 2.",
        3,
        True,
    ),
    (
        "04_out_of_range",
        "Combining [1], [2] and [9] (the bibliography only has three entries).",
        3,
        True,
    ),
    (
        "05_descending_and_duplicate",
        "A reverse range [3-1] and a doubled id [2, 2] both look fluent in prose.",
        5,
        True,
    ),
    (
        "06_non_numeric_inside_bracket",
        "Some authors write [1, x] when they mean to insert an id later.",
        3,
        True,
    ),
    (
        "07_stray_close_bracket",
        "An accidental ] with no opener is easy to miss.",
        3,
        True,
    ),
    (
        "08_dense_off",
        "Sources [1] and [3] only — but require_dense_sequence is off so no skipped_id fires.",
        3,
        False,
    ),
]


def _run_demo() -> None:
    print("# llm-output-citation-bracket-balance-validator — worked example")
    print()
    for name, prose, max_id, dense in _CASES:
        print(f"## case {name}")
        print(f"prose: {prose!r}")
        print(f"max_id={max_id}, require_dense_sequence={dense}")
        result = validate(prose, max_id=max_id, require_dense_sequence=dense)
        print(result.to_json())
        print()


if __name__ == "__main__":
    _run_demo()
