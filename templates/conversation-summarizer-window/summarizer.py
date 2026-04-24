#!/usr/bin/env python3
"""Conversation summarizer-window: drop-and-summarize when context > N%.

The classic problem: a long-running agent conversation grows past the
model's context window. Naive truncation (drop oldest messages) loses
important early instructions and decisions. This template implements
the standard "summarize the dropped tail into a synthetic
`[summary]` system message, keep the recent tail verbatim" pattern,
with explicit and testable trigger rules.

Pure stdlib. Deterministic: caller injects the token-counter and the
summarizer function — no LLM calls inside the primitive. That keeps
this unit-testable and lets the same code work with any tokenizer
(approx, tiktoken, sentencepiece, ...).

Trigger rule:
    when total_tokens >= ceil(window_tokens * trigger_pct):
        summarize the OLDEST dropable messages until
        total_tokens <= ceil(window_tokens * target_pct)

Pinned messages (system prompt, anchored decisions) are NEVER dropped.
The synthetic summary message replaces the dropped block in-place.

CLI:
    python summarizer.py demo
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass
class Message:
    role: str               # "system" | "user" | "assistant" | "tool" | "summary"
    content: str
    pinned: bool = False    # True => never drop, never summarize away
    msg_id: str = ""        # caller-supplied id for traceability


def default_token_counter(text: str) -> int:
    # Crude but stable: ~ 4 chars per token. Real users inject tiktoken etc.
    return max(1, math.ceil(len(text) / 4))


@dataclass
class SummarizerWindow:
    window_tokens: int                # model context budget (tokens)
    trigger_pct: float                # e.g. 0.80 — compress when >= this fraction
    target_pct: float                 # e.g. 0.50 — compress until <= this fraction
    summarize_fn: Callable[[list[Message]], str]
    token_counter: Callable[[str], int] = field(default=default_token_counter)

    def __post_init__(self) -> None:
        if not (0.0 < self.target_pct < self.trigger_pct <= 1.0):
            raise ValueError("require 0 < target_pct < trigger_pct <= 1")
        if self.window_tokens <= 0:
            raise ValueError("window_tokens must be > 0")

    def total_tokens(self, msgs: Iterable[Message]) -> int:
        return sum(self.token_counter(m.content) for m in msgs)

    def should_compress(self, msgs: list[Message]) -> bool:
        return self.total_tokens(msgs) >= math.ceil(
            self.window_tokens * self.trigger_pct
        )

    def compress(self, msgs: list[Message]) -> tuple[list[Message], dict]:
        """Return (new_msgs, report). new_msgs has dropped tail replaced by
        a single synthetic 'summary' message. Pinned messages are preserved
        in their original order."""
        target = math.ceil(self.window_tokens * self.target_pct)
        if self.total_tokens(msgs) <= target:
            return list(msgs), {
                "compressed": False,
                "reason": "already_under_target",
                "tokens_before": self.total_tokens(msgs),
                "tokens_after": self.total_tokens(msgs),
                "dropped_count": 0,
            }

        # Strategy: walk from oldest non-pinned forward, accumulating into
        # the "to-summarize" bucket, until removing them brings total under
        # target. Stop early if we've drained all droppable old messages.
        # Recent messages (kept verbatim) are everything from the first
        # non-droppable message we hit going from newest to oldest, unless
        # we have to dip further.
        # Simpler & predictable: accumulate oldest droppable until under target.

        kept: list[Message] = list(msgs)
        to_summarize: list[Message] = []

        # Scan oldest -> newest, peeling droppable messages.
        i = 0
        while i < len(kept) and self.total_tokens(kept) > target:
            m = kept[i]
            if m.pinned or m.role == "summary":
                i += 1
                continue
            to_summarize.append(m)
            kept.pop(i)
            # Don't increment i — we just removed kept[i]. But also reserve
            # token budget for the summary we'll inject. Approximate the
            # summary as ~ 1/4 of what it summarizes.
            approx_summary_tokens = max(
                1, sum(self.token_counter(x.content) for x in to_summarize) // 4
            )
            projected = self.total_tokens(kept) + approx_summary_tokens
            if projected <= target:
                break

        if not to_summarize:
            return list(msgs), {
                "compressed": False,
                "reason": "nothing_droppable",
                "tokens_before": self.total_tokens(msgs),
                "tokens_after": self.total_tokens(msgs),
                "dropped_count": 0,
            }

        summary_text = self.summarize_fn(to_summarize)
        summary_msg = Message(
            role="summary",
            content=summary_text,
            pinned=False,
            msg_id=f"summary_of_{len(to_summarize)}",
        )

        # Insert the summary message at the position of the first kept
        # non-pinned, non-summary message (i.e. just before the recent tail),
        # preserving pinned-system-prompts at the top.
        insert_at = 0
        for idx, m in enumerate(kept):
            if not m.pinned and m.role != "summary":
                insert_at = idx
                break
            insert_at = idx + 1
        kept.insert(insert_at, summary_msg)

        return kept, {
            "compressed": True,
            "reason": "trigger_met",
            "tokens_before": self.total_tokens(msgs),
            "tokens_after": self.total_tokens(kept),
            "dropped_count": len(to_summarize),
            "dropped_ids": [m.msg_id for m in to_summarize],
            "summary_inserted_at": insert_at,
        }


# --- demo ---------------------------------------------------------------

def _fake_summarizer(msgs: list[Message]) -> str:
    parts = [f"{m.role}:{m.msg_id}" for m in msgs]
    return f"[summary of {len(msgs)} dropped msgs: {', '.join(parts)}]"


def _demo() -> int:
    sw = SummarizerWindow(
        window_tokens=400,
        trigger_pct=0.80,
        target_pct=0.50,
        summarize_fn=_fake_summarizer,
    )
    msgs = [
        Message("system", "You are a helpful assistant. " * 5, pinned=True, msg_id="sys"),
        Message("user", "Question 1: " + "x" * 200, msg_id="u1"),
        Message("assistant", "Answer 1: " + "y" * 200, msg_id="a1"),
        Message("user", "Question 2: " + "x" * 200, msg_id="u2"),
        Message("assistant", "Answer 2: " + "y" * 200, msg_id="a2"),
        Message("user", "Question 3 (recent): short", msg_id="u3"),
    ]
    print(json.dumps({"total_before": sw.total_tokens(msgs), "should_compress": sw.should_compress(msgs)}, sort_keys=True))
    new_msgs, report = sw.compress(msgs)
    print(json.dumps(report, sort_keys=True))
    for m in new_msgs:
        print(json.dumps({"role": m.role, "msg_id": m.msg_id, "tokens": default_token_counter(m.content), "pinned": m.pinned}, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] == "demo":
        return _demo()
    print("usage: python summarizer.py demo", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
