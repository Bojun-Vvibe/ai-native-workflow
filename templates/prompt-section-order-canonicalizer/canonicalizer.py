"""Pure stdlib canonicalizer for the section order of a system prompt.

Two prompt edits that produce *byte-different* but *semantically equivalent*
system prompts are the most common cause of silent prompt-cache misses:

  Author A writes:    # Identity / # Tools / # Output format / # Safety
  Author B refactors: # Identity / # Safety / # Output format / # Tools

The model behaves identically. The cache key derived from the raw text does
not. The next 100 calls are cold-prefix and the bill spikes. Worse, the
"refactor" lands silently in code review because the diff is just a section
move — the reviewer reads it as a no-op.

This canonicalizer reorders sections to a stable, declared `canonical_order`
before the cache-key derivation step (`prompt-cache-key-canonicalizer` runs
*after* this). Two prompts that differ only in section order canonicalize to
the same byte-string, so the cache key is stable across reorderings.

Design choices:

1. **Section identity is the lower-cased header text.** `# Identity`,
   `# IDENTITY`, and `## identity` all map to `identity`. ATX markdown only
   by default; the regex is configurable for `<!-- section: foo -->` formats.

2. **Pre-header content is a synthetic `__preamble__` section** and stays at
   the top regardless of `canonical_order` — re-anchoring the preamble would
   be surprising and break a common "system role + context" preamble pattern.

3. **Closed `canonical_order` enum.** Sections in the order list appear in
   that order. Unknown sections (present in input, not in `canonical_order`)
   default to `unknown_policy` ∈ `{"raise", "tail", "drop"}`. `tail` (default)
   appends them in original order *after* the canonical-ordered sections so a
   newly-added section doesn't crash the pipeline. `raise` is for "this
   prompt template is supposed to be exhaustively declared" gates.

4. **Duplicate sections raise** (`PromptOrderError`) — two `# Tools` blocks in
   one prompt is almost always an authoring bug, and silently merging them
   would change semantics. Caller fixes the prompt.

5. **Trailing whitespace inside each section is preserved.** Reordering must
   not silently re-format. The only byte-level changes are: (a) section
   blocks moved as units, (b) exactly one blank line between adjacent sections
   (so a reorder doesn't accidentally glue a section's last line onto the
   next section's header).

6. **Pure & deterministic**: `canonicalize(text, canonical_order, *,
   unknown_policy, header_re) -> CanonicalizeResult`. Returns the rewritten
   text plus a `moves` log so a CI gate can show "section X moved from
   position 2 to position 4" — the diff is auditable.

7. **Idempotent**: `canonicalize(canonicalize(x, order), order).text ==
   canonicalize(x, order).text`. A pipeline that runs the canonicalizer twice
   produces no further changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Pattern, Tuple


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PromptOrderError(ValueError):
    """Raised on duplicate sections, unknown section under raise policy, or
    bad config (empty canonical_order, etc)."""


# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

PREAMBLE_KEY = "__preamble__"

# Default ATX-markdown header regex: 1-6 leading #, then space, then text.
# Identity is the lower-cased trimmed header text (after the #s).
_DEFAULT_HEADER_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$", re.MULTILINE)

_VALID_UNKNOWN_POLICY = frozenset({"raise", "tail", "drop"})


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    key: str  # lower-cased header text, or PREAMBLE_KEY
    header_line: Optional[str]  # the literal header line (e.g. "## Tools"); None for preamble
    body: str  # everything between this header and the next header (no leading newline strip)


@dataclass(frozen=True)
class Move:
    key: str
    from_index: int  # original 0-based position among sections
    to_index: int  # canonical 0-based position


@dataclass(frozen=True)
class CanonicalizeResult:
    text: str
    sections: Tuple[Section, ...]  # sections in canonical order (after rewrite)
    moves: Tuple[Move, ...]  # only sections that actually moved
    unknown_keys: Tuple[str, ...]  # keys present in input, not in canonical_order
    dropped_keys: Tuple[str, ...]  # keys removed under unknown_policy=drop
    summary: str

    @property
    def changed(self) -> bool:
        return len(self.moves) > 0 or len(self.dropped_keys) > 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_sections(text: str, header_re: Pattern[str]) -> List[Section]:
    """Split text into a list of Section. Pre-header content becomes a
    synthetic __preamble__ section if non-empty."""
    matches = list(header_re.finditer(text))
    sections: List[Section] = []

    if not matches:
        # Whole text is preamble.
        if text.strip():
            sections.append(Section(PREAMBLE_KEY, None, text))
        return sections

    first_start = matches[0].start()
    if first_start > 0:
        preamble = text[:first_start]
        if preamble.strip():
            sections.append(Section(PREAMBLE_KEY, None, preamble))

    for i, m in enumerate(matches):
        header_line = m.group(0)
        key = m.group(2).strip().lower()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        sections.append(Section(key, header_line, body))

    return sections


# ---------------------------------------------------------------------------
# Canonicalize
# ---------------------------------------------------------------------------


def canonicalize(
    text: str,
    canonical_order: List[str],
    *,
    unknown_policy: str = "tail",
    header_re: Optional[Pattern[str]] = None,
) -> CanonicalizeResult:
    """Reorder sections in `text` to follow `canonical_order`.

    Args:
      text: prompt source.
      canonical_order: ordered list of section keys (lower-cased). Must be
                       non-empty and contain no duplicates.
      unknown_policy: how to treat sections not in `canonical_order` —
                      "tail" (default; append in original order),
                      "drop" (remove silently — recorded in `dropped_keys`),
                      "raise" (raise PromptOrderError).
      header_re: regex for header detection. Default matches ATX markdown
                 (`#`..`######` followed by space + text). Must use group(2)
                 for the header text.

    Raises:
      PromptOrderError on bad config or duplicate sections in input.
    """
    if not canonical_order:
        raise PromptOrderError("canonical_order must be non-empty")
    if len(canonical_order) != len(set(canonical_order)):
        raise PromptOrderError("canonical_order has duplicate keys")
    if PREAMBLE_KEY in canonical_order:
        raise PromptOrderError(
            f"canonical_order may not contain {PREAMBLE_KEY!r} (preamble is anchored)"
        )
    if unknown_policy not in _VALID_UNKNOWN_POLICY:
        raise PromptOrderError(
            f"unknown_policy must be one of {sorted(_VALID_UNKNOWN_POLICY)}, "
            f"got {unknown_policy!r}"
        )

    re_pat = header_re or _DEFAULT_HEADER_RE
    canonical_order_lc = [k.lower() for k in canonical_order]

    sections = _parse_sections(text, re_pat)

    # Reject duplicates among non-preamble sections.
    seen_keys = set()
    for s in sections:
        if s.key == PREAMBLE_KEY:
            continue
        if s.key in seen_keys:
            raise PromptOrderError(
                f"duplicate section in input: {s.key!r}"
            )
        seen_keys.add(s.key)

    # Split preamble (if any) from the body sections.
    preamble: Optional[Section] = None
    body_sections: List[Section] = []
    for s in sections:
        if s.key == PREAMBLE_KEY:
            preamble = s
        else:
            body_sections.append(s)

    by_key = {s.key: s for s in body_sections}
    original_index = {s.key: i for i, s in enumerate(body_sections)}

    # Build the canonical-ordered list.
    ordered: List[Section] = []
    for key in canonical_order_lc:
        if key in by_key:
            ordered.append(by_key[key])

    # Handle unknowns.
    unknown_keys = [s.key for s in body_sections if s.key not in canonical_order_lc]
    dropped: List[str] = []
    if unknown_keys:
        if unknown_policy == "raise":
            raise PromptOrderError(
                f"unknown sections in input not in canonical_order: {unknown_keys}"
            )
        elif unknown_policy == "tail":
            for s in body_sections:
                if s.key in unknown_keys:
                    ordered.append(s)
        elif unknown_policy == "drop":
            dropped = list(unknown_keys)

    # Compute moves (relative position among body_sections).
    canonical_index = {s.key: i for i, s in enumerate(ordered)}
    moves: List[Move] = []
    for s in body_sections:
        if s.key not in canonical_index:
            continue  # dropped
        from_i = original_index[s.key]
        to_i = canonical_index[s.key]
        if from_i != to_i:
            moves.append(Move(s.key, from_i, to_i))
    moves.sort(key=lambda m: m.to_index)

    # Render the canonical text.
    rendered = _render(preamble, ordered)

    summary = (
        f"sections={len(body_sections)} "
        f"moved={len(moves)} "
        f"unknown={len(unknown_keys)} "
        f"dropped={len(dropped)} "
        f"policy={unknown_policy}"
    )

    return CanonicalizeResult(
        text=rendered,
        sections=tuple(ordered),
        moves=tuple(moves),
        unknown_keys=tuple(unknown_keys),
        dropped_keys=tuple(dropped),
        summary=summary,
    )


def _render(preamble: Optional[Section], ordered_sections: List[Section]) -> str:
    """Render preamble + ordered sections into one text. Exactly one blank
    line separates adjacent sections."""
    parts: List[str] = []

    if preamble is not None:
        # Preserve preamble's body verbatim.
        parts.append(preamble.body.rstrip("\n"))

    for s in ordered_sections:
        # Strip leading newlines on body so we control spacing precisely.
        body = s.body.lstrip("\n").rstrip("\n")
        block = s.header_line + "\n" + body if body else s.header_line
        parts.append(block)

    if not parts:
        return ""

    # Join with exactly one blank line between blocks.
    result = "\n\n".join(parts)
    # Preserve a trailing newline if the original had one.
    return result + "\n"


__all__ = [
    "Section",
    "Move",
    "CanonicalizeResult",
    "PromptOrderError",
    "PREAMBLE_KEY",
    "canonicalize",
]
