"""Example 1: clean doc with one missing citation and one orphan footnote."""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from citations import scan  # type: ignore


DOC = """\
# On long-context retrieval

Recent work [^vaswani] has shown that scaled dot-product attention
generalizes to context windows well past 100k tokens, though the
empirical degradation curve is steeper than the original paper [^vaswani]
implies. Independent reproductions [^reprod-2024] confirm the finding,
and a follow-up survey [^never-defined] expands on the result.

[^vaswani]: Vaswani et al., "Attention is All You Need", NeurIPS 2017.
[^reprod-2024]: Independent benchmark, Lab X, 2024.
[^orphan-note]: This footnote is defined but never cited in the body.
"""

report = scan(DOC)
print("--- summary ---")
print(report.summary)
print("--- referenced (in first-seen order) ---")
print(list(report.referenced_ids))
print("--- defined (in first-seen order) ---")
print(list(report.defined_ids))
print("--- use_counts ---")
print(json.dumps(report.use_counts, indent=2, sort_keys=True))
print("--- missing_definitions ---")
print(list(report.missing_definitions))
print("--- orphan_definitions ---")
print(list(report.orphan_definitions))
print("--- duplicate_definitions ---")
print(json.dumps(report.duplicate_definitions, indent=2, sort_keys=True))

assert report.has_broken is True, "expected has_broken=True (one missing)"
assert "never-defined" in report.missing_definitions
assert "orphan-note" in report.orphan_definitions
assert report.use_counts["vaswani"] == 2
print("--- has_broken ---")
print(report.has_broken)
