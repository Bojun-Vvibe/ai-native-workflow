"""Worked example: tool-name-typo-suggester.

Five scenarios covering the verdict surface:

1. Exact match (`read_file` -> exact)
2. Single-char substitution (`read_fle` -> read_file, distance 1)
3. Adjacent transposition (`raed_file` -> read_file, distance 1)
4. Ambiguous: two candidates tied at distance 1 (`reqd_file`)
5. Unknown: no candidate within max_distance (`launch_nukes`)
6. Bonus: registry collision rejected at construction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from suggester import TypoSuggester, Suggestion


REGISTRY = [
    "read_file",
    "read_files",     # plural sibling
    "write_file",
    "list_dir",
    "run_shell",
    "search_grep",
    "delete_file",
]


def _show(label: str, name: str, sug: Suggestion) -> None:
    print(f"--- {label} ---")
    print(f"input:    {name!r}")
    print(f"verdict:  {sug.verdict}")
    print(f"best:     {sug.best!r}")
    print(f"distance: {sug.distance}")
    print(f"runners:  {sug.runners_up}")
    print(f"reason:   {sug.reason}")
    print()


def main() -> None:
    s = TypoSuggester(REGISTRY, max_distance=2, tie_break_margin=1)
    print(f"registry: {s.known_names}")
    print()

    # 1. Exact match.
    _show("1. exact", "read_file", s.suggest("read_file"))

    # 2. Single-char substitution.
    _show("2. substitution", "read_fle", s.suggest("read_fle"))

    # 3. Adjacent transposition.
    _show("3. transposition", "raed_file", s.suggest("raed_file"))

    # 4. Ambiguous: `reqd_file` is distance 1 from `read_file` (substitution e->q)
    #    AND distance 1 from `delete_file`? no, that's much further. Try a real
    #    ambiguity: `read_file` vs `read_files` from input `read_filex`:
    #      - read_file:  distance 1 (delete x)
    #      - read_files: distance 1 (substitute x->s)
    _show("4. ambiguous", "read_filex", s.suggest("read_filex"))

    # 5. Unknown.
    _show("5. unknown", "launch_nukes", s.suggest("launch_nukes"))

    # 6. Registry collision rejected at construction:
    #    `Read_File` and `read_file` normalize to the same key.
    print("--- 6. registry collision rejected ---")
    try:
        TypoSuggester(["read_file", "Read_File"])
    except ValueError as e:
        print(f"raised ValueError as expected: {e}")
    print()

    # Invariants check.
    print("--- invariants ---")
    sug_exact = s.suggest("READ_FILE")  # case-folded
    assert sug_exact.verdict == "exact", "case-fold should still match exact"
    print(f"case-fold exact match: {sug_exact.best!r} (passes)")

    sug_empty = s.suggest("")
    assert sug_empty.verdict == "unknown"
    print(f"empty input -> verdict=unknown (passes)")

    # Demo wiring: how a host would consume the suggestion.
    print()
    print("--- host wiring demo ---")
    incoming = "read_fle"
    sug = s.suggest(incoming)
    if sug.verdict == "exact":
        print(f"dispatch {incoming!r} -> tool {sug.best!r}")
    elif sug.verdict == "suggestion":
        msg = {
            "error": "unknown_tool",
            "received": incoming,
            "suggestion": sug.best,
            "distance": sug.distance,
            "hint": f"Did you mean {sug.best!r}?",
        }
        print(json.dumps(msg, indent=2))
    else:
        msg = {
            "error": "unknown_tool",
            "received": incoming,
            "candidates": sug.runners_up,
            "hint": "No close match" if not sug.runners_up else "Multiple close candidates; please pick one",
        }
        print(json.dumps(msg, indent=2))


if __name__ == "__main__":
    main()
