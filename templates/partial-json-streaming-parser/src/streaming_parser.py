"""partial-json-streaming-parser

Incrementally parse a JSON object that arrives in chunks (as from a
streaming model output), exposing the *current best-effort view* of
the object after every chunk.

Use case: you ask the model for `{"plan": [...], "answer": "..."}`,
the response streams in token-by-token, and you want to render the
plan to the user as soon as it's complete — without waiting for the
trailing `"answer"` field, and without crashing if the stream is cut
mid-string.

Public API:
    parser = StreamingJSONParser()
    parser.feed(chunk)        # call repeatedly with raw text chunks
    parser.snapshot()         # -> dict | list | None  (best-effort)
    parser.complete           # -> bool
    parser.tail               # -> str  (unconsumed buffer; useful for debug)

Strategy: at each `feed`, attempt to *close* the open structures by
appending the minimal sequence of `"`, `]`, and `}` characters that
would make the buffer parse, then `json.loads` the closed string.
If that fails, return the previous good snapshot. This is the
"prefix-completion" approach used by several streaming agent UIs.

Limitations (be honest):
- Numbers truncated mid-token (e.g. `1.`) are rejected by `json.loads`;
  we trim trailing partial number tokens before closing.
- Unicode escapes truncated mid-sequence (`\\u00`) are trimmed.
- A backslash at the very end is trimmed (mid-escape).
- Does NOT handle JSON streams (NDJSON) — that's a different problem,
  use a line splitter.

Pure stdlib.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


# Trailing fragments we strip before attempting to close the JSON.
# Order matters: try the longest cleanup first.
_TRAILING_NUMBER = re.compile(r"(?<![\"\\])(?:-?\d+\.?\d*[eE]?[+\-]?\d*)$")
_TRAILING_UNICODE_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{0,3}$")


@dataclass
class StreamingJSONParser:
    buffer: str = ""
    _last_good: object = None
    complete: bool = False
    _last_full_attempt_failed: bool = False
    history: list[object] = field(default_factory=list)

    def feed(self, chunk: str) -> object:
        if self.complete:
            # Allow noise after a successful complete parse, ignore it.
            return self._last_good
        self.buffer += chunk
        self._try_full_parse()
        if not self.complete:
            self._try_partial_parse()
        return self._last_good

    @property
    def tail(self) -> str:
        return self.buffer

    def snapshot(self) -> object:
        return self._last_good

    # --- internals ------------------------------------------------

    def _try_full_parse(self) -> None:
        s = self.buffer.strip()
        if not s:
            return
        try:
            self._last_good = json.loads(s)
            self.complete = True
            self.history.append(self._last_good)
        except json.JSONDecodeError:
            return

    def _try_partial_parse(self) -> None:
        s = self.buffer
        # Walk left-to-right tracking string state and bracket stack.
        stack: list[str] = []  # stack of '{' or '['
        in_string = False
        escape_next = False
        for ch in s:
            if escape_next:
                escape_next = False
                continue
            if in_string:
                if ch == "\\":
                    escape_next = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()

        # Take the buffer up to a "safe" cut point and synthesize a
        # closing suffix.
        candidate = s

        # If we ended mid-escape inside a string, drop the dangling backslash.
        if in_string and escape_next:
            candidate = candidate[:-1]
        # Trim a partial unicode escape inside a string.
        if in_string:
            candidate = _TRAILING_UNICODE_ESCAPE.sub("", candidate)

        # If we ended on a partial number outside a string, trim it. JSON
        # rejects e.g. `1.` and `1e`. We only trim if it would otherwise
        # be the *last* token before a closing bracket.
        if not in_string:
            stripped = candidate.rstrip()
            # Only consider if stripped doesn't end in a structural char
            # that would already terminate the number.
            if stripped and stripped[-1] not in "}],\"":
                m = _TRAILING_NUMBER.search(stripped)
                if m:
                    tok = m.group(0)
                    # Trim if it's not a complete number — i.e., ends
                    # with `.`, `e`, `E`, `+`, `-`.
                    if tok and tok[-1] in ".eE+-":
                        candidate = stripped[: m.start()]
                        # also drop a dangling `,` or `:` that would
                        # otherwise leave invalid syntax
                        candidate = candidate.rstrip().rstrip(",:")

        # Also strip a trailing `,` or `:` outside a string — those
        # leave the structure non-parseable.
        if not in_string:
            cand_stripped = candidate.rstrip()
            while cand_stripped.endswith((",", ":")):
                cand_stripped = cand_stripped[:-1].rstrip()
            candidate = cand_stripped

        # Close any open string, then close the bracket stack.
        suffix_parts: list[str] = []
        if in_string:
            suffix_parts.append('"')
        for opener in reversed(stack):
            suffix_parts.append("}" if opener == "{" else "]")
        synth = candidate + "".join(suffix_parts)

        try:
            obj = json.loads(synth)
        except json.JSONDecodeError:
            self._last_full_attempt_failed = True
            return

        self._last_good = obj
        self.history.append(obj)
        self._last_full_attempt_failed = False
