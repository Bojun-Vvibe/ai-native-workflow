"""
llm-streaming-chunk-boundary-validator
======================================

Validate that a *recorded* sequence of streamed chunks (SSE / NDJSON /
raw token stream) splits at boundaries that are safe for incremental
display **and** for incremental JSON parsing. Fires on the four classes
of split that silently corrupt downstream consumers:

  - utf8_split          : a chunk's tail or the next chunk's head bisects
                          a multi-byte UTF-8 sequence (terminal renders
                          mojibake; naive byte-by-byte JSON parser blows
                          up at the next decode call)
  - inside_string       : a chunk boundary lands *inside* a JSON string
                          literal in declared structured-output mode
                          (the streaming JSON repair / extraction layer
                          may emit a half-string token and let it leak
                          to the UI)
  - escape_split        : a JSON `\\` escape character is the last byte
                          of a chunk and its escapee is the first byte
                          of the next (`\\` + `n` reassembled, but a
                          chunk-at-a-time consumer that decodes early
                          mis-emits a literal backslash)
  - codepoint_grapheme  : a chunk ends mid-emoji-ZWJ-sequence (e.g.
                          family emoji `👨‍👩‍👧`) — the joiner sits in
                          the next chunk and the user's terminal renders
                          two separate glyphs for ~150ms. A soft warning;
                          flips ok=False but is not a parser bug.

Pure stdlib. Operates on a list of `bytes` chunks (the wire form). The
caller may pass `mode="text"` for free-form prose (only utf8_split and
codepoint_grapheme apply) or `mode="json"` for declared structured
output (all four apply, and inside_string / escape_split are tracked
across chunks via a tiny streaming state machine).

This is a *post-hoc* validator over recorded chunks — it does not own
the transport. Pair with `streaming-chunk-reassembler` (transport
layer) and `partial-json-streaming-parser` (consumer layer); this is
the regression / fixture validator that proves your splits are safe
before you ship them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class ChunkValidationError(ValueError):
    """Malformed input (not bytes, unknown mode)."""


Mode = Literal["text", "json"]


@dataclass(frozen=True)
class BoundaryFinding:
    kind: str             # utf8_split | inside_string | escape_split | codepoint_grapheme
    boundary_index: int   # 0-based: 0 = boundary between chunk[0] and chunk[1]
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "boundary_index": self.boundary_index,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BoundaryReport:
    ok: bool
    chunk_count: int
    boundary_count: int
    mode: str
    findings: tuple[BoundaryFinding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "chunk_count": self.chunk_count,
            "boundary_count": self.boundary_count,
            "mode": self.mode,
            "findings": [f.to_dict() for f in self.findings],
        }


# UTF-8 leading byte → expected sequence length (1..4). Continuation bytes
# (10xxxxxx) are not valid leaders and signal a *mid-sequence* boundary.
def _utf8_seq_len(byte: int) -> int | None:
    if byte < 0x80:
        return 1
    if byte < 0xC0:
        return None  # continuation byte — never a leader
    if byte < 0xE0:
        return 2
    if byte < 0xF0:
        return 3
    if byte < 0xF8:
        return 4
    return None


def _ends_mid_utf8(chunk: bytes) -> tuple[bool, str]:
    """
    Walk the tail of `chunk`: if the last leader byte's expected sequence
    length exceeds what is present, the boundary is mid-codepoint.
    """
    if not chunk:
        return False, ""
    # Find the last leader (non-continuation) byte
    i = len(chunk) - 1
    while i >= 0 and 0x80 <= chunk[i] < 0xC0:
        i -= 1
    if i < 0:
        # Entire chunk is continuation bytes — the *previous* chunk was the
        # actual mid-codepoint split; we still flag here for completeness.
        return True, "tail consists entirely of UTF-8 continuation bytes"
    leader = chunk[i]
    expected = _utf8_seq_len(leader)
    if expected is None:
        return True, f"invalid UTF-8 leader byte 0x{leader:02X} at tail"
    have = len(chunk) - i
    if have < expected:
        return True, (
            f"leader 0x{leader:02X} expects {expected}-byte sequence, "
            f"only {have} byte(s) before chunk boundary"
        )
    return False, ""


# Zero-Width Joiner sits between glyph components in family / profession
# emoji sequences. A chunk that ends with one (or whose next chunk starts
# with one) split a grapheme cluster.
_ZWJ = b"\xe2\x80\x8d"  # U+200D in UTF-8


def _ends_with_zwj(chunk: bytes) -> bool:
    return chunk.endswith(_ZWJ)


def _starts_with_zwj(chunk: bytes) -> bool:
    return chunk.startswith(_ZWJ)


def _scan_json_state(prefix: bytes, in_string: bool, escape: bool) -> tuple[bool, bool]:
    """
    Update (in_string, escape) state by scanning `prefix`.
    Only quote / backslash / non-backslash matter for *boundary* classification.
    We do not validate the JSON itself.
    """
    for b in prefix:
        if escape:
            # The escapee was consumed; back to normal in-string scanning
            escape = False
            continue
        if in_string:
            if b == 0x5C:  # backslash
                escape = True
            elif b == 0x22:  # double quote — string closes
                in_string = False
        else:
            if b == 0x22:  # string opens
                in_string = True
    return in_string, escape


def validate(chunks: list[bytes], *, mode: Mode = "text") -> BoundaryReport:
    if not isinstance(chunks, list):
        raise ChunkValidationError("chunks must be a list")
    if mode not in ("text", "json"):
        raise ChunkValidationError(f"unknown mode {mode!r}")
    for i, c in enumerate(chunks):
        if not isinstance(c, (bytes, bytearray)):
            raise ChunkValidationError(f"chunks[{i}] is not bytes")

    findings: list[BoundaryFinding] = []
    boundaries = max(0, len(chunks) - 1)

    in_string = False
    escape = False

    for bi in range(boundaries):
        left = bytes(chunks[bi])
        right = bytes(chunks[bi + 1])

        # --- utf8_split: left ends mid-codepoint ---
        bad, why = _ends_mid_utf8(left)
        if bad:
            findings.append(
                BoundaryFinding(
                    kind="utf8_split", boundary_index=bi, detail=why
                )
            )

        # --- codepoint_grapheme: ZWJ straddles boundary ---
        if _ends_with_zwj(left) or _starts_with_zwj(right):
            findings.append(
                BoundaryFinding(
                    kind="codepoint_grapheme",
                    boundary_index=bi,
                    detail=(
                        "ZWJ (U+200D) straddles boundary; emoji sequence will "
                        "render as separate glyphs in the consumer for one tick"
                    ),
                )
            )

        # --- json-mode-only: state-machine boundary checks ---
        if mode == "json":
            # Scan everything up to and including `left` to know post-left state
            in_string, escape = _scan_json_state(left, in_string, escape)

            if in_string:
                findings.append(
                    BoundaryFinding(
                        kind="inside_string",
                        boundary_index=bi,
                        detail=(
                            "boundary lands inside a JSON string literal; a "
                            "naive consumer may emit a partial string token"
                        ),
                    )
                )
            if escape:
                findings.append(
                    BoundaryFinding(
                        kind="escape_split",
                        boundary_index=bi,
                        detail=(
                            "boundary lands immediately after a JSON `\\` "
                            "escape; the escapee byte is the first byte of "
                            "the next chunk"
                        ),
                    )
                )

    findings.sort(key=lambda f: (f.boundary_index, f.kind))

    return BoundaryReport(
        ok=len(findings) == 0,
        chunk_count=len(chunks),
        boundary_count=boundaries,
        mode=mode,
        findings=tuple(findings),
    )
