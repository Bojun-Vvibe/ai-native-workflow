"""Worked example for json-schema-required-field-coverage-reporter.

Schema: a "code-review summary" object the LLM is asked to emit, with nested
required fields including an array-of-objects.

Corpus: 10 synthetic LLM outputs hand-crafted to exhibit realistic failure
modes — missing top-level fields, null values, wrong types, empty arrays, and
missing per-element required fields. The report should rank the most-forgotten
field first.
"""

from __future__ import annotations

from reporter import report_json, report


SCHEMA = {
    "type": "object",
    "required": ["verdict", "summary", "findings", "metadata"],
    "properties": {
        "verdict": {"type": "string"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "line", "severity"],
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {"type": "string"},
                },
            },
        },
        "metadata": {
            "type": "object",
            "required": ["model", "elapsed_ms"],
            "properties": {
                "model": {"type": "string"},
                "elapsed_ms": {"type": "integer"},
            },
        },
    },
}


# 10 docs with intentional pathologies.
DOCS = [
    # 1. clean
    {
        "verdict": "approve",
        "summary": "looks good",
        "findings": [{"file": "a.py", "line": 12, "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 200},
    },
    # 2. missing summary
    {
        "verdict": "approve",
        "findings": [{"file": "a.py", "line": 12, "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 210},
    },
    # 3. summary is null
    {
        "verdict": "request_changes",
        "summary": None,
        "findings": [{"file": "b.py", "line": 5, "severity": "warn"}],
        "metadata": {"model": "m1", "elapsed_ms": 305},
    },
    # 4. missing summary AND missing metadata.elapsed_ms
    {
        "verdict": "approve",
        "findings": [{"file": "c.py", "line": 1, "severity": "info"}],
        "metadata": {"model": "m1"},
    },
    # 5. findings is empty array → missing per-element fields
    {
        "verdict": "approve",
        "summary": "no issues",
        "findings": [],
        "metadata": {"model": "m1", "elapsed_ms": 100},
    },
    # 6. one finding missing `severity`
    {
        "verdict": "approve",
        "summary": "ok",
        "findings": [{"file": "d.py", "line": 9}],
        "metadata": {"model": "m1", "elapsed_ms": 150},
    },
    # 7. wrong type: line is a string
    {
        "verdict": "approve",
        "summary": "ok",
        "findings": [{"file": "e.py", "line": "9", "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 175},
    },
    # 8. missing summary
    {
        "verdict": "approve",
        "findings": [{"file": "f.py", "line": 3, "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 220},
    },
    # 9. missing summary
    {
        "verdict": "approve",
        "findings": [{"file": "g.py", "line": 4, "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 230},
    },
    # 10. clean
    {
        "verdict": "approve",
        "summary": "fine",
        "findings": [{"file": "h.py", "line": 7, "severity": "info"}],
        "metadata": {"model": "m1", "elapsed_ms": 240},
    },
]


def main() -> None:
    print("=" * 72)
    print("Coverage report — 10-document corpus against code-review schema")
    print("=" * 72)
    print(report_json(SCHEMA, DOCS))

    # Runtime invariants — fail loud if the engine miscounts.
    r = report(SCHEMA, DOCS)
    n = r.documents_total
    assert n == 10, n
    by_path = {f.path: f for f in r.fields}

    # /summary missing in docs 2, 4, 8, 9 → 4; null in doc 3 → 1; present 5.
    s = by_path["/summary"]
    assert (s.missing, s.null, s.present, s.wrong_type) == (4, 1, 5, 0), (
        s.missing, s.null, s.present, s.wrong_type
    )

    # /findings[]/severity missing in docs 5 (empty array) and 6 → 2.
    sev = by_path["/findings[]/severity"]
    assert sev.missing == 2, sev.missing

    # /findings[]/line wrong_type in doc 7, missing in doc 5 (empty array).
    line = by_path["/findings[]/line"]
    assert (line.missing, line.wrong_type) == (1, 1), (line.missing, line.wrong_type)

    # /metadata/elapsed_ms missing in doc 4 only → 1.
    em = by_path["/metadata/elapsed_ms"]
    assert em.missing == 1, em.missing

    worst = r.worst_offender
    assert worst is not None
    assert worst.path == "/summary", worst.path
    print()
    print(f"INVARIANTS OK — worst offender: {worst.path} "
          f"(missing+null+wrong_type rate "
          f"{(worst.missing + worst.null + worst.wrong_type) / n:.2f})")


if __name__ == "__main__":
    main()
