"""
Priority-aware prompt section trimmer.

Assemble a final prompt from labeled sections (system, instructions,
retrieved docs, conversation turns, scratchpad...) under a hard token
budget. When the budget is exceeded, trim from the LOW-priority end
deterministically, optionally truncating a single section in the middle
of the priority ladder rather than dropping it whole.

Token counting is pluggable. Default is whitespace-split, which is
intentionally crude but stdlib-only and good enough for tests + docs.
Wire in your real tokenizer in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple


def default_count(text: str) -> int:
    """Crude tokenizer: whitespace split. Replace in production."""
    return len(text.split())


@dataclass(frozen=True)
class Section:
    label: str           # e.g. "system", "retrieved_doc_3", "turn_42"
    text: str
    priority: int        # higher = keep first; lower = drop first
    truncatable: bool = False  # if True, can be partially kept on the boundary


@dataclass
class TrimResult:
    sections: List[Section]          # final ordered sections (post-trim)
    kept_labels: List[str]           # labels kept (possibly partially)
    dropped_labels: List[str]        # labels dropped entirely
    truncated_label: Optional[str]   # label whose body was cut, if any
    total_tokens: int
    budget: int

    def assemble(self, joiner: str = "\n\n") -> str:
        return joiner.join(s.text for s in self.sections)


class PromptBudgetTrimmer:
    """
    Deterministic priority-aware trimmer.

    Algorithm:
      1. Sort sections by (priority desc, original_index asc).
      2. Greedily admit highest-priority sections until adding the
         next one would exceed `budget`.
      3. If the next section is `truncatable`, keep a head-prefix of
         it sized exactly to the remaining slack, with an explicit
         "[...truncated N tokens]" marker (counted against budget).
      4. Drop everything below.
      5. Re-emit kept sections in original input order so the prompt
         reads naturally.
    """

    def __init__(
        self,
        budget: int,
        count: Callable[[str], int] = default_count,
        truncation_marker: str = "[...truncated {n} tokens]",
    ) -> None:
        if budget <= 0:
            raise ValueError("budget must be positive")
        self.budget = budget
        self.count = count
        self.truncation_marker = truncation_marker

    def trim(self, sections: List[Section]) -> TrimResult:
        indexed: List[Tuple[int, Section]] = list(enumerate(sections))
        # Stable sort: priority desc, then original order asc
        ordered = sorted(indexed, key=lambda iv: (-iv[1].priority, iv[0]))

        kept: List[Tuple[int, Section]] = []
        dropped: List[str] = []
        truncated_label: Optional[str] = None
        used = 0

        for orig_idx, sec in ordered:
            cost = self.count(sec.text)
            if used + cost <= self.budget:
                kept.append((orig_idx, sec))
                used += cost
                continue

            slack = self.budget - used
            if sec.truncatable and slack > 0:
                head, head_tokens, dropped_tokens = self._truncate(
                    sec.text, slack
                )
                if head_tokens > 0:
                    marker = self.truncation_marker.format(n=dropped_tokens)
                    new_text = f"{head}\n{marker}"
                    new_cost = self.count(new_text)
                    # Final safety: if the marker pushes us over, shave more.
                    while new_cost > slack and head_tokens > 0:
                        head_tokens -= 1
                        head_words = head.split()
                        head = " ".join(head_words[:head_tokens])
                        dropped_tokens = self.count(sec.text) - head_tokens
                        marker = self.truncation_marker.format(n=dropped_tokens)
                        new_text = f"{head}\n{marker}".strip()
                        new_cost = self.count(new_text)
                    if new_cost > 0 and new_cost <= slack:
                        kept.append(
                            (orig_idx, Section(sec.label, new_text,
                                               sec.priority, True))
                        )
                        used += new_cost
                        truncated_label = sec.label
                        continue
            dropped.append(sec.label)

        # Re-emit in original order
        kept.sort(key=lambda iv: iv[0])
        final_sections = [s for _, s in kept]
        kept_labels = [s.label for s in final_sections]

        # Anything not in kept and not in dropped was after a truncation;
        # mark them dropped too.
        seen = set(kept_labels) | set(dropped)
        for s in sections:
            if s.label not in seen:
                dropped.append(s.label)

        return TrimResult(
            sections=final_sections,
            kept_labels=kept_labels,
            dropped_labels=dropped,
            truncated_label=truncated_label,
            total_tokens=used,
            budget=self.budget,
        )

    def _truncate(self, text: str, slack: int) -> Tuple[str, int, int]:
        """Keep at most `slack` tokens of head; return (head, head_tok, dropped_tok)."""
        words = text.split()
        total = len(words)
        # Reserve ~6 tokens for the marker line; never go negative.
        head_budget = max(0, slack - 6)
        head_words = words[:head_budget]
        head = " ".join(head_words)
        head_tok = len(head_words)
        dropped_tok = total - head_tok
        return head, head_tok, dropped_tok
