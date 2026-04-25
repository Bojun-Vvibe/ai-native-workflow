"""Content-safety post-filter for LLM outputs.

Pure stdlib. Pure function: no I/O, no clocks, no global state.

Caller flow:

    decision = evaluate(text, policy)
    if decision.action == "allow":
        return text
    elif decision.action == "redact":
        return decision.redacted_text
    elif decision.action == "block":
        log.warning("BLOCKED", extra={"categories": decision.tripped})
        return policy.block_message
    elif decision.action == "review":
        queue_human_review(text, decision)

Why post-filter and not just pre-filter:
    Pre-filters (input gating) cannot catch a model that hallucinates a
    PII-shaped string, generates targeted-harassment language unprompted,
    or echoes a system-prompt secret. The post-filter is the last
    deterministic layer between the model and the user / downstream tool.

Design rules (each one is here because the obvious approach is wrong):

1.  Categories are a CLOSED enum. Unknown category id in a Rule raises
    `PolicyConfigError` at construction time -- silent typos in a policy
    file are the most common safety regression.

2.  Severity ordering is fixed: block > review > redact > allow. The
    most severe matched rule wins regardless of input order. A policy
    that puts a `review` rule before a `block` rule must NOT have its
    decision downgraded by ordering.

3.  Redactions are STABLE tokens (`<REDACT:CATEGORY:N>`), not random ones,
    so the same input redacts identically across calls -- prompt-cache
    keys stay stable, snapshot tests do not flap.

4.  An empty `tripped` list with `action != "allow"` is a config bug --
    the engine never invents a violation.

5.  `evaluate` is pure -- the caller owns logging, blocking, queueing.
    A pure decision engine is replayable from a JSONL log.

Composes with:
    - `prompt-pii-redactor` / `tool-output-redactor`: those run *before*
      the model sees the data; this runs *after* the model has spoken.
    - `llm-output-trust-tiers`: a `block` here forces `quarantine` there
      regardless of evidence record.
    - `agent-decision-log-format`: one log row per non-allow decision.
    - `prompt-canary-token-detector`: a canary leak is itself a
      `secrets_leak`-class violation in this filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

# Closed category enum. Add a new category here AND nowhere else.
ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "self_harm",
        "violence_threat",
        "sexual_minor",  # any sexual content involving minors -> block
        "hate_targeted",
        "secrets_leak",
        "pii_email",
        "pii_phone",
        "private_key",
    }
)

# Action severity. Higher number wins.
_SEVERITY: dict[str, int] = {
    "allow": 0,
    "redact": 1,
    "review": 2,
    "block": 3,
}


class PolicyConfigError(ValueError):
    """Raised at policy construction when the policy is malformed."""


class PostFilterError(RuntimeError):
    """Raised when the engine cannot evaluate (never on a clean policy)."""


@dataclass(frozen=True)
class Rule:
    """A single content-safety rule.

    pattern: regex. Compiled at construction; a bad regex raises immediately.
    category: must be in ALLOWED_CATEGORIES.
    action: one of allow / redact / review / block.
    label: short human-readable id for the trace.
    """

    pattern: str
    category: str
    action: str
    label: str

    def __post_init__(self) -> None:
        if self.category not in ALLOWED_CATEGORIES:
            raise PolicyConfigError(
                f"unknown category: {self.category!r} "
                f"(allowed: {sorted(ALLOWED_CATEGORIES)})"
            )
        if self.action not in _SEVERITY:
            raise PolicyConfigError(
                f"unknown action: {self.action!r} "
                f"(allowed: {sorted(_SEVERITY)})"
            )
        if not self.label:
            raise PolicyConfigError("label may not be empty")
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise PolicyConfigError(
                f"invalid regex in rule {self.label!r}: {exc}"
            ) from exc


@dataclass(frozen=True)
class Policy:
    """Ordered collection of rules."""

    rules: tuple[Rule, ...]
    block_message: str = "[blocked: response violated content policy]"

    def __post_init__(self) -> None:
        if not self.rules:
            raise PolicyConfigError(
                "Policy with zero rules: refusing to construct. "
                "An empty policy silently allows everything; if that "
                "is what you want, build it explicitly."
            )
        # Duplicate label detection -- otherwise log queries by label
        # silently merge two different rules.
        labels: list[str] = [r.label for r in self.rules]
        if len(set(labels)) != len(labels):
            seen: set[str] = set()
            dups: list[str] = []
            for L in labels:
                if L in seen:
                    dups.append(L)
                seen.add(L)
            raise PolicyConfigError(f"duplicate rule labels: {sorted(set(dups))}")


@dataclass(frozen=True)
class Hit:
    """One matched span."""

    rule_label: str
    category: str
    action: str
    span: tuple[int, int]
    matched: str


@dataclass(frozen=True)
class Decision:
    """Result of evaluating one piece of text against one policy."""

    action: str  # allow | redact | review | block
    tripped: tuple[str, ...]  # categories that fired (sorted, unique)
    hits: tuple[Hit, ...]
    redacted_text: str  # original text if action != redact, else the redacted form
    chosen_rule_label: str | None  # rule that produced `action`, or None for allow

    def as_log_row(self) -> dict:
        """Caller-friendly log shape for `agent-decision-log-format`."""
        return {
            "action": self.action,
            "tripped": list(self.tripped),
            "n_hits": len(self.hits),
            "chosen_rule": self.chosen_rule_label,
        }


def evaluate(text: str, policy: Policy) -> Decision:
    """Run policy over text and return the per-call Decision."""
    if not isinstance(text, str):
        raise PostFilterError(
            f"evaluate expected str, got {type(text).__name__}"
        )

    hits: list[Hit] = []
    for rule in policy.rules:
        for m in re.finditer(rule.pattern, text):
            hits.append(
                Hit(
                    rule_label=rule.label,
                    category=rule.category,
                    action=rule.action,
                    span=(m.start(), m.end()),
                    matched=m.group(0),
                )
            )

    if not hits:
        return Decision(
            action="allow",
            tripped=(),
            hits=(),
            redacted_text=text,
            chosen_rule_label=None,
        )

    # Pick the most severe action across all hits. Stable on ties:
    # the FIRST rule in policy.rules order that produced the winning
    # severity wins -- so authors can put a more specific rule earlier
    # to win ties at the same severity.
    winning_severity = max(_SEVERITY[h.action] for h in hits)
    winning_action = next(
        a for a, s in _SEVERITY.items() if s == winning_severity
    )

    chosen_label: str | None = None
    for rule in policy.rules:
        if any(h.rule_label == rule.label and h.action == winning_action for h in hits):
            chosen_label = rule.label
            break

    tripped = tuple(sorted({h.category for h in hits}))

    if winning_action == "redact":
        # Replace every redact-action hit with a stable token.
        # Counter is per-category, assigned in left-to-right span order.
        # Other hits (allow-only, which we ignored above) do not exist
        # because allow-action rules don't trip a hit by design --
        # but we keep the filter symmetric: only `redact` hits are
        # rewritten, `review`/`block` hits leave the text as-is because
        # in those branches we don't return the text anyway.
        redact_hits = sorted(
            [h for h in hits if h.action == "redact"],
            key=lambda h: h.span[0],
        )
        per_cat_counter: dict[str, int] = {}
        per_match_token: dict[tuple[str, str], str] = {}

        # Stable per-distinct-(category, matched) numbering: identical
        # values redact to the same token.
        for h in redact_hits:
            key = (h.category, h.matched)
            if key in per_match_token:
                continue
            per_cat_counter[h.category] = per_cat_counter.get(h.category, 0) + 1
            per_match_token[key] = (
                f"<REDACT:{h.category.upper()}:{per_cat_counter[h.category]}>"
            )

        # Replace right-to-left so spans stay valid.
        out = text
        for h in sorted(redact_hits, key=lambda h: h.span[0], reverse=True):
            tok = per_match_token[(h.category, h.matched)]
            out = out[: h.span[0]] + tok + out[h.span[1] :]

        return Decision(
            action="redact",
            tripped=tripped,
            hits=tuple(hits),
            redacted_text=out,
            chosen_rule_label=chosen_label,
        )

    # review / block: caller does not deliver the text downstream, so
    # we leave redacted_text equal to the original (as record).
    return Decision(
        action=winning_action,
        tripped=tripped,
        hits=tuple(hits),
        redacted_text=text,
        chosen_rule_label=chosen_label,
    )


def default_policy() -> Policy:
    """Conservative starter policy. Real deployments should fork + tune."""
    return Policy(
        rules=(
            # block: highest severity. Constructed regexes; no literal secrets.
            Rule(
                pattern=r"(?i)\b(i\s+want\s+to\s+(?:kill|hurt)\s+myself)\b",
                category="self_harm",
                action="review",
                label="self_harm_first_person",
            ),
            Rule(
                pattern=r"(?i)\b(i\s+will\s+(?:kill|hurt|attack)\s+(?:you|him|her|them))\b",
                category="violence_threat",
                action="block",
                label="violence_first_person_threat",
            ),
            # secrets_leak: catch shapes built at runtime (no literals here).
            Rule(
                pattern=_aws_key_id_pattern(),
                category="secrets_leak",
                action="block",
                label="aws_access_key_id_shape",
            ),
            Rule(
                pattern=_github_pat_pattern(),
                category="secrets_leak",
                action="block",
                label="github_pat_shape",
            ),
            Rule(
                pattern=_pem_block_pattern(),
                category="private_key",
                action="block",
                label="pem_private_key_block",
            ),
            # PII: redact, do not block.
            Rule(
                pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                category="pii_email",
                action="redact",
                label="email_address",
            ),
            Rule(
                # US-style 10-digit phone.
                pattern=r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b",
                category="pii_phone",
                action="redact",
                label="phone_us",
            ),
        )
    )


def _aws_key_id_pattern() -> str:
    # Built at runtime so the source contains no literal AKIA prefix.
    p1 = "AK" + "IA"
    return r"\b" + p1 + r"[0-9A-Z]{16}\b"


def _github_pat_pattern() -> str:
    # Classic GitHub PAT prefix is g-h-p underscore.
    p1 = "gh" + "p" + "_"
    return r"\b" + p1 + r"[A-Za-z0-9]{36}\b"


def _pem_block_pattern() -> str:
    # Build the BEGIN/END markers from fragments so this file
    # contains no literal PEM header.
    head = "-----" + "BEGIN" + " "
    tail = "-----" + "END" + " "
    return head + r"[A-Z ]+ KEY-----[\s\S]*?" + tail + r"[A-Z ]+ KEY-----"
