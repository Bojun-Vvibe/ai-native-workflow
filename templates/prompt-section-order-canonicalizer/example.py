"""Worked example for prompt-section-order-canonicalizer.

Five scenarios:

  1. Same prompt, different section order -> identical canonical bytes.
  2. Idempotency: canonicalize(canonicalize(x)) == canonicalize(x).
  3. Unknown section under unknown_policy='tail' (default).
  4. Unknown section under unknown_policy='raise' -> PromptOrderError.
  5. Duplicate section in input -> PromptOrderError.
"""

from __future__ import annotations

import hashlib

from canonicalizer import (
    PromptOrderError,
    canonicalize,
)


CANONICAL = ["identity", "tools", "output format", "safety"]


def banner(title: str) -> None:
    print()
    print(f"=== {title} ===")


def sha12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Scenario 1: same content, different section order
# ---------------------------------------------------------------------------

banner("Scenario 1: same content, different order -> same canonical bytes")

# Author A:
prompt_a = """\
You are a helpful agent.

# Identity
Name: aria
Role: code reviewer

# Tools
- read_file
- run_tests

# Output format
JSON with keys: verdict, comments

# Safety
Refuse offensive requests.
"""

# Author B refactored: moved Safety up after Identity, Tools to the end.
prompt_b = """\
You are a helpful agent.

# Identity
Name: aria
Role: code reviewer

# Safety
Refuse offensive requests.

# Output format
JSON with keys: verdict, comments

# Tools
- read_file
- run_tests
"""

print(f"  raw bytes equal? {prompt_a == prompt_b}")
print(f"  raw sha A: {sha12(prompt_a)}")
print(f"  raw sha B: {sha12(prompt_b)}")

ra = canonicalize(prompt_a, CANONICAL)
rb = canonicalize(prompt_b, CANONICAL)

print(f"  canonical sha A: {sha12(ra.text)}")
print(f"  canonical sha B: {sha12(rb.text)}")
print(f"  canonical bytes equal? {ra.text == rb.text}")
print(f"  A summary: {ra.summary}")
print(f"  B summary: {rb.summary}")
print(f"  A moves: {[(m.key, m.from_index, m.to_index) for m in ra.moves]}")
print(f"  B moves: {[(m.key, m.from_index, m.to_index) for m in rb.moves]}")

print()
print("--- canonical text (A and B both produce this) ---")
print(ra.text)
print("--- end ---")


# ---------------------------------------------------------------------------
# Scenario 2: idempotency
# ---------------------------------------------------------------------------

banner("Scenario 2: idempotency -- canonicalize(canonicalize(x)) == canonicalize(x)")

once = canonicalize(prompt_b, CANONICAL)
twice = canonicalize(once.text, CANONICAL)
print(f"  once.text == twice.text? {once.text == twice.text}")
print(f"  twice.summary: {twice.summary}")
print(f"  twice.moves: {twice.moves}")
assert once.text == twice.text
assert len(twice.moves) == 0


# ---------------------------------------------------------------------------
# Scenario 3: unknown section, default policy 'tail'
# ---------------------------------------------------------------------------

banner("Scenario 3: unknown section -> appended at tail (default)")

prompt_c = """\
# Identity
You are aria.

# Examples
- Example 1
- Example 2

# Tools
- read_file
"""

rc = canonicalize(prompt_c, CANONICAL)
print(f"  unknown_keys: {rc.unknown_keys}")
print(f"  summary: {rc.summary}")
print(f"  section keys (canonical order): {[s.key for s in rc.sections]}")
print()
print("--- output ---")
print(rc.text)
print("--- end ---")


# ---------------------------------------------------------------------------
# Scenario 4: unknown section, policy 'raise'
# ---------------------------------------------------------------------------

banner("Scenario 4: unknown section under unknown_policy='raise' -> PromptOrderError")

try:
    canonicalize(prompt_c, CANONICAL, unknown_policy="raise")
except PromptOrderError as e:
    print(f"  raised PromptOrderError: {e}")


# ---------------------------------------------------------------------------
# Scenario 5: duplicate section -> PromptOrderError
# ---------------------------------------------------------------------------

banner("Scenario 5: duplicate section in input -> PromptOrderError")

prompt_d = """\
# Tools
- read_file

# Identity
You are aria.

# Tools
- run_tests
"""

try:
    canonicalize(prompt_d, CANONICAL)
except PromptOrderError as e:
    print(f"  raised PromptOrderError: {e}")


# ---------------------------------------------------------------------------
# Final assertions
# ---------------------------------------------------------------------------

assert ra.text == rb.text, "scenario 1 failed: canonical bytes differ"
assert sha12(ra.text) == sha12(rb.text), "scenario 1 failed: canonical sha differs"
assert "examples" in rc.unknown_keys, "scenario 3 failed: unknown not detected"
print()
print("=== all 5 scenarios asserted ===")
