"""partial-json-tail-recovery — heuristically close a truncated JSON object/array.

A streaming LLM that hits ``max_tokens`` mid-emission produces a JSON blob whose
*tail* is structurally incomplete: an unclosed object, an unfinished string, a
trailing comma, a half-typed key. The bytes already received are usually
**fine** up to some prefix; we want to recover that prefix as a parseable
object and tell the caller exactly which top-level keys are
**confirmed-complete** (their value was fully closed by the model itself) vs
**heuristically-closed** (we patched braces/brackets to make the tail parse).

Stdlib-only. No regexes for string scanning — a hand-rolled state machine so
escapes and unicode escapes inside strings are honored correctly.

Public API
----------
- ``recover(text: str) -> RecoveryResult``
- ``RecoveryResult.parsed: dict | list | None``
- ``RecoveryResult.confirmed_keys: list[str]`` — top-level keys whose value was
  closed by the *model*, before any patching
- ``RecoveryResult.heuristic_keys: list[str]`` — top-level keys whose value we
  had to close ourselves (or whose value got dropped because it was a bare
  partial token like ``tr``)
- ``RecoveryResult.dropped_tail: str`` — the raw bytes after the last clean
  cut-point
- ``RecoveryResult.actions: list[str]`` — ordered patches applied
- ``RecoveryResult.status: str`` — one of ``"clean"`` (input already parsed),
  ``"recovered"`` (parsed after patching), ``"unrecoverable"`` (we gave up)

Design rules
------------
1. We never *invent* a value. If the tail is ``"name": "Al`` we drop the
   whole ``name`` key — we will not guess ``"Alice"``.
2. We close in LIFO order. If the open-stack at the cut is ``[{ , [ , {``
   we emit ``}``, ``]``, ``}``.
3. A trailing comma at the cut point is dropped, not preserved.
4. A half-written key (``"na``) at the cut is dropped along with anything
   after it.
5. ``confirmed_keys`` is computed from the **input prefix** (pre-patch), not
   the patched output, so the caller can trust it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class RecoveryResult:
    parsed: object | None
    confirmed_keys: list[str]
    heuristic_keys: list[str]
    dropped_tail: str
    actions: list[str]
    status: str

    def to_dict(self) -> dict:
        return {
            "parsed": self.parsed,
            "confirmed_keys": list(self.confirmed_keys),
            "heuristic_keys": list(self.heuristic_keys),
            "dropped_tail": self.dropped_tail,
            "actions": list(self.actions),
            "status": self.status,
        }


@dataclass
class _ScanState:
    # stack of opener chars: '{' or '['
    stack: list[str] = field(default_factory=list)
    # for objects: the index in stack -> last fully-committed key name (or None)
    in_string: bool = False
    string_quote_pos: int = -1
    escape_next: bool = False
    # last character index that is the end of a fully-parseable prefix
    last_safe_cut: int = 0
    # track per-object phase: "expect_key" | "in_key" | "expect_colon"
    # | "expect_value" | "in_value" | "after_value"
    # We keep a parallel stack of phases for objects.
    phase_stack: list[str] = field(default_factory=list)
    # parallel stack: keys committed at this object level
    keys_stack: list[list[str]] = field(default_factory=list)
    # parallel: pending key text (when in_key) at this object level
    pending_key_stack: list[str | None] = field(default_factory=list)
    # for arrays we still push a phase ("array") to keep depth aligned
    # Top-level (depth 0) committed keys for the *outermost* object
    top_committed_keys: list[str] = field(default_factory=list)


def _scan(text: str) -> tuple[_ScanState, int]:
    """Walk the text, tracking structure. Returns (state, cut_index).

    ``cut_index`` is the largest index ``i`` such that ``text[:i]`` ends at a
    clean boundary (after a value, after ``,``, etc.) at the *current* depth.
    The caller patches by truncating to ``cut_index`` and emitting closers.
    """
    s = _ScanState()
    i = 0
    n = len(text)

    def _open_obj():
        s.stack.append("{")
        s.phase_stack.append("expect_key")
        s.keys_stack.append([])
        s.pending_key_stack.append(None)

    def _open_arr():
        s.stack.append("[")
        s.phase_stack.append("expect_value")
        s.keys_stack.append([])
        s.pending_key_stack.append(None)

    def _close_top():
        opener = s.stack.pop()
        s.phase_stack.pop()
        committed = s.keys_stack.pop()
        s.pending_key_stack.pop()
        # If we just closed the outermost object, record committed keys.
        if not s.stack and opener == "{":
            s.top_committed_keys = list(committed)
        # Tell parent we just finished a value, AND commit parent's pending
        # key (the value that just closed *was* the parent's value).
        if s.phase_stack:
            s.phase_stack[-1] = "after_value"
            if s.stack and s.stack[-1] == "{":
                pk = s.pending_key_stack[-1]
                if pk is not None:
                    s.keys_stack[-1].append(pk)
                    s.pending_key_stack[-1] = None

    while i < n:
        c = text[i]

        if s.in_string:
            if s.escape_next:
                s.escape_next = False
                i += 1
                continue
            if c == "\\":
                s.escape_next = True
                i += 1
                continue
            if c == '"':
                s.in_string = False
                # Decide whether this string was a key or a value.
                if s.phase_stack and s.phase_stack[-1] == "in_key":
                    raw = text[s.string_quote_pos : i + 1]
                    try:
                        key_name = json.loads(raw)
                    except Exception:
                        key_name = raw[1:-1]
                    s.pending_key_stack[-1] = key_name
                    s.phase_stack[-1] = "expect_colon"
                elif s.phase_stack and s.phase_stack[-1] == "in_value":
                    # commit pending key if we are inside an object
                    if s.stack and s.stack[-1] == "{":
                        pk = s.pending_key_stack[-1]
                        if pk is not None:
                            s.keys_stack[-1].append(pk)
                            s.pending_key_stack[-1] = None
                    s.phase_stack[-1] = "after_value"
                    s.last_safe_cut = i + 1
                i += 1
                continue
            i += 1
            continue

        if c.isspace():
            i += 1
            continue

        if c == '"':
            s.in_string = True
            s.string_quote_pos = i
            if s.phase_stack and s.phase_stack[-1] == "expect_key":
                s.phase_stack[-1] = "in_key"
            elif s.phase_stack and s.phase_stack[-1] == "expect_value":
                s.phase_stack[-1] = "in_value"
            i += 1
            continue

        if c == "{":
            if s.phase_stack and s.phase_stack[-1] == "expect_value":
                s.phase_stack[-1] = "in_value"
                # NOTE: do NOT commit the parent key yet. The key is only
                # "confirmed" when its value finishes parsing (close brace).
            _open_obj()
            i += 1
            continue

        if c == "[":
            if s.phase_stack and s.phase_stack[-1] == "expect_value":
                s.phase_stack[-1] = "in_value"
            _open_arr()
            i += 1
            continue

        if c == "}":
            _close_top()
            s.last_safe_cut = i + 1
            i += 1
            continue

        if c == "]":
            _close_top()
            s.last_safe_cut = i + 1
            i += 1
            continue

        if c == ":":
            if s.phase_stack and s.phase_stack[-1] == "expect_colon":
                s.phase_stack[-1] = "expect_value"
            i += 1
            continue

        if c == ",":
            if s.phase_stack:
                top = s.stack[-1]
                if top == "{":
                    s.phase_stack[-1] = "expect_key"
                else:
                    s.phase_stack[-1] = "expect_value"
                s.last_safe_cut = i  # cut BEFORE the comma
            i += 1
            continue

        # bare literal: number, true, false, null
        # walk until non-bare char
        j = i
        while j < n and text[j] not in ',]}\n\r\t " :':
            j += 1
        token = text[i:j]
        if j == n:
            # truncated mid-literal -> do not commit
            i = j
            continue
        # try to parse it
        try:
            json.loads(token)
            ok = True
        except Exception:
            ok = False
        if ok:
            if s.stack and s.stack[-1] == "{":
                pk = s.pending_key_stack[-1]
                if pk is not None:
                    s.keys_stack[-1].append(pk)
                    s.pending_key_stack[-1] = None
            if s.phase_stack:
                s.phase_stack[-1] = "after_value"
            s.last_safe_cut = j
        i = j
        continue

    return s, s.last_safe_cut


def recover(text: str) -> RecoveryResult:
    if not text or not text.strip():
        return RecoveryResult(None, [], [], text, [], "unrecoverable")

    # Fast path: already valid?
    try:
        parsed = json.loads(text)
        confirmed: list[str] = []
        if isinstance(parsed, dict):
            confirmed = list(parsed.keys())
        return RecoveryResult(parsed, confirmed, [], "", [], "clean")
    except Exception:
        pass

    state, cut = _scan(text)
    actions: list[str] = []
    head = text[:cut]
    dropped = text[cut:]
    if dropped:
        actions.append(f"dropped tail: {dropped!r}")

    # confirmed keys = keys committed at the OUTERMOST object level
    if state.stack and state.stack[0] == "{":
        confirmed = list(state.keys_stack[0]) if state.keys_stack else []
    elif not state.stack:
        # outermost was already closed by the model
        confirmed = list(state.top_committed_keys)
    else:
        confirmed = []

    # close remaining openers in LIFO order
    closers = []
    for opener in reversed(state.stack):
        if opener == "{":
            closers.append("}")
        else:
            closers.append("]")
    if closers:
        actions.append(f"appended closers: {''.join(closers)}")
    patched = head + "".join(closers)

    if not patched.strip():
        return RecoveryResult(None, [], [], dropped, actions, "unrecoverable")

    try:
        parsed = json.loads(patched)
    except Exception as e:
        actions.append(f"final parse failed: {e}")
        return RecoveryResult(None, confirmed, [], dropped, actions, "unrecoverable")

    # heuristic_keys = keys that ended up in parsed but were NOT in confirmed.
    heuristic: list[str] = []
    if isinstance(parsed, dict):
        for k in parsed.keys():
            if k not in confirmed:
                heuristic.append(k)

    return RecoveryResult(parsed, confirmed, heuristic, dropped, actions, "recovered")
