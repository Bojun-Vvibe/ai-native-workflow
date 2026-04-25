"""Example 2: same id defined twice with conflicting payloads (collision).

A repeated-verbatim definition is harmless and is NOT flagged.
A repeated id with a *different* payload is flagged in duplicate_definitions
because it means the document silently picks one source over the other.
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from citations import scan  # type: ignore


DOC = """\
The benchmark [^bench] reports a 12% improvement, while a contemporaneous
re-evaluation [^bench] reports the opposite sign. The follow-up [^followup]
splits the difference. The verbatim-redefinition case [^verbatim] should
not raise an alarm.

[^bench]: https://example.org/bench-paper-A.pdf
[^bench]: https://example.org/bench-paper-B.pdf
[^followup]: Lab Y, 2025.
[^verbatim]: https://example.org/v.pdf
[^verbatim]: https://example.org/v.pdf
"""

report = scan(DOC)
print("--- summary ---")
print(report.summary)
print("--- duplicate_definitions ---")
print(json.dumps(report.duplicate_definitions, indent=2, sort_keys=True))
print("--- missing_definitions ---")
print(list(report.missing_definitions))
print("--- orphan_definitions ---")
print(list(report.orphan_definitions))
print("--- has_broken ---")
print(report.has_broken)

assert "bench" in report.duplicate_definitions, "bench should be flagged (distinct payloads)"
assert "verbatim" not in report.duplicate_definitions, "verbatim repeat should not be flagged"
assert report.has_broken is True
assert report.missing_definitions == ()
assert report.orphan_definitions == ()
print("OK")
