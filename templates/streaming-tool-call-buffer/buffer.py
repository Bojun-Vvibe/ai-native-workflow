"""Streaming tool-call buffer.

LLM streaming APIs (OpenAI-compatible, Anthropic, etc.) emit tool-call
deltas as JSON-fragment chunks. A single tool call's `arguments` field
is split across many deltas, possibly interleaved with other tool calls
(by `index`), and only becomes valid JSON once the whole stream finishes
that call.

This module:
  - Accumulates per-(call_index) name + arguments fragments.
  - Detects when a call is "complete" (stream advances past it OR the
    accumulated arguments parse as JSON AND a finalize signal arrives).
  - Emits each completed call exactly once via a callback.
  - Surfaces malformed calls instead of silently dropping them.

Pure stdlib. Safe to drop into a host that bridges streaming model
output into a tool dispatcher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class _PartialCall:
    index: int
    call_id: Optional[str] = None
    name: Optional[str] = None
    args_buf: str = ""
    finalized: bool = False
    emitted: bool = False


@dataclass
class CompletedCall:
    index: int
    call_id: Optional[str]
    name: str
    arguments: dict


@dataclass
class MalformedCall:
    index: int
    call_id: Optional[str]
    name: Optional[str]
    raw_arguments: str
    error: str


class StreamingToolCallBuffer:
    """Buffer streaming tool-call deltas; emit each call exactly once.

    Usage:
        buf = StreamingToolCallBuffer(on_complete=dispatch,
                                      on_malformed=quarantine)
        for delta in stream:
            buf.feed(delta)
        buf.finish()  # flushes any remaining complete calls
    """

    def __init__(
        self,
        on_complete: Callable[[CompletedCall], None],
        on_malformed: Optional[Callable[[MalformedCall], None]] = None,
    ) -> None:
        self._on_complete = on_complete
        self._on_malformed = on_malformed or (lambda _m: None)
        self._calls: Dict[int, _PartialCall] = {}
        self._highest_seen_index: int = -1

    # Delta shape (loosely OpenAI-compatible):
    #   {"index": int, "id": str?, "name": str?, "arguments": str?,
    #    "finalize": bool?}
    # Anthropic-style streams can be normalized into this before feeding.
    def feed(self, delta: dict) -> None:
        idx = delta.get("index")
        if idx is None:
            # Some providers omit index when there's only one call.
            idx = 0
        call = self._calls.get(idx)
        if call is None:
            call = _PartialCall(index=idx)
            self._calls[idx] = call

        if "id" in delta and delta["id"]:
            call.call_id = delta["id"]
        if "name" in delta and delta["name"]:
            call.name = delta["name"]
        if "arguments" in delta and delta["arguments"]:
            call.args_buf += delta["arguments"]
        if delta.get("finalize"):
            call.finalized = True

        # If the stream advances to a higher index, any earlier call
        # that has parseable JSON args is implicitly complete.
        if idx > self._highest_seen_index:
            self._highest_seen_index = idx
            for prev_idx, prev in list(self._calls.items()):
                if prev_idx < idx and not prev.emitted:
                    self._try_emit(prev, implicit=True)

        if call.finalized:
            self._try_emit(call, implicit=False)

    def finish(self) -> None:
        """Stream ended. Try to emit anything still buffered."""
        for call in self._calls.values():
            if not call.emitted:
                self._try_emit(call, implicit=True, end_of_stream=True)

    def _try_emit(
        self,
        call: _PartialCall,
        implicit: bool,
        end_of_stream: bool = False,
    ) -> None:
        if call.emitted:
            return
        if not call.name:
            if end_of_stream:
                call.emitted = True
                self._on_malformed(
                    MalformedCall(
                        index=call.index,
                        call_id=call.call_id,
                        name=None,
                        raw_arguments=call.args_buf,
                        error="missing tool name at end of stream",
                    )
                )
            # Otherwise wait — name may arrive in a later delta.
            return

        # Empty arguments are valid for zero-arg tools.
        raw = call.args_buf.strip()
        if not raw:
            if call.finalized or end_of_stream or implicit:
                call.emitted = True
                self._on_complete(
                    CompletedCall(
                        index=call.index,
                        call_id=call.call_id,
                        name=call.name,
                        arguments={},
                    )
                )
            return

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            if call.finalized or end_of_stream:
                call.emitted = True
                self._on_malformed(
                    MalformedCall(
                        index=call.index,
                        call_id=call.call_id,
                        name=call.name,
                        raw_arguments=raw,
                        error=f"invalid JSON: {exc.msg} at pos {exc.pos}",
                    )
                )
            # Implicit-only completion with bad JSON: keep waiting.
            return

        if not isinstance(parsed, dict):
            call.emitted = True
            self._on_malformed(
                MalformedCall(
                    index=call.index,
                    call_id=call.call_id,
                    name=call.name,
                    raw_arguments=raw,
                    error="arguments must be a JSON object",
                )
            )
            return

        call.emitted = True
        self._on_complete(
            CompletedCall(
                index=call.index,
                call_id=call.call_id,
                name=call.name,
                arguments=parsed,
            )
        )
