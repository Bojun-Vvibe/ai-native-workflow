"""Pure validator for the role sequence of a multi-turn chat prompt.

Rules enforced (deterministic, first-match-wins per message position):

  R1  empty_messages       — message list is empty
  R2  bad_first_role       — first message is not `system` (when require_system=True)
                             or first message is not in {system,user} (when require_system=False)
  R3  duplicate_system     — more than one `system` message, OR a `system` message
                             appears after position 0
  R4  consecutive_assistant — two assistant messages in a row (model talking to itself
                             is almost always a state-machine bug)
  R5  consecutive_user      — two user messages in a row (lost assistant turn)
  R6  tool_without_call    — `tool` message whose immediately-preceding assistant
                             did not declare a matching `tool_call_id` in its
                             `tool_calls` list
  R7  unanswered_tool_call — assistant declared `tool_calls=[id1,id2,...]` but the
                             very next non-assistant messages do not include a
                             `tool` reply for *every* declared id before the next
                             assistant or user turn
  R8  unknown_role          — role not in {system,user,assistant,tool}
  R9  empty_content_non_tool_call — assistant message with no content AND no
                                    tool_calls (a no-op turn)
  R10 trailing_assistant_with_open_tool_calls — last message is an assistant with
      tool_calls but the conversation ended before the tool replied (caller most
      likely truncated the trace mid-flight)

The validator returns a `ValidationResult(ok, errors, warnings)`. It never raises
on bad input — a malformed prompt is a structured failure, not a stack trace,
because this gate runs *before* the prompt is sent and the caller wants to log
the reason and either repair or refuse.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


_KNOWN_ROLES = frozenset({"system", "user", "assistant", "tool"})


@dataclass
class Issue:
    code: str
    index: int  # message index the issue is anchored at; -1 for whole-list issues
    detail: str

    def to_dict(self) -> dict:
        return {"code": self.code, "index": self.index, "detail": self.detail}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


def _role(msg: Any) -> str | None:
    if not isinstance(msg, dict):
        return None
    r = msg.get("role")
    return r if isinstance(r, str) else None


def _tool_call_ids(msg: dict) -> list[str]:
    calls = msg.get("tool_calls")
    if not isinstance(calls, list):
        return []
    out: list[str] = []
    for c in calls:
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            out.append(c["id"])
    return out


def validate(messages: Iterable[Any], *, require_system: bool = True) -> ValidationResult:
    msgs = list(messages)
    errors: list[Issue] = []
    warnings: list[Issue] = []

    if not msgs:
        errors.append(Issue("empty_messages", -1, "message list is empty"))
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    # First-message role check (R2)
    first_role = _role(msgs[0])
    if first_role is None or first_role not in _KNOWN_ROLES:
        errors.append(
            Issue(
                "unknown_role",
                0,
                f"first message has missing/unknown role: {first_role!r}",
            )
        )
    elif require_system and first_role != "system":
        errors.append(
            Issue(
                "bad_first_role",
                0,
                f"first message must be 'system', got {first_role!r}",
            )
        )
    elif (not require_system) and first_role not in ("system", "user"):
        errors.append(
            Issue(
                "bad_first_role",
                0,
                f"first message must be 'system' or 'user', got {first_role!r}",
            )
        )

    # System occurrences (R3)
    system_indices = [i for i, m in enumerate(msgs) if _role(m) == "system"]
    if len(system_indices) > 1:
        for i in system_indices[1:]:
            errors.append(
                Issue("duplicate_system", i, "additional 'system' message after position 0")
            )
    elif len(system_indices) == 1 and system_indices[0] != 0:
        errors.append(
            Issue(
                "duplicate_system",
                system_indices[0],
                "'system' message must be at position 0",
            )
        )

    # Walk the sequence and apply per-position rules.
    pending_tool_call_ids: list[str] = []
    pending_tool_call_assistant_idx: int | None = None

    for i, msg in enumerate(msgs):
        role = _role(msg)
        if role is None or role not in _KNOWN_ROLES:
            # R8 — but we already flagged position 0 above; flag others here.
            if i != 0:
                errors.append(
                    Issue("unknown_role", i, f"role missing or not in known set: {role!r}")
                )
            # Skip further per-message rules for this position.
            continue

        if role == "assistant":
            # R4 consecutive assistant
            if i > 0 and _role(msgs[i - 1]) == "assistant":
                errors.append(
                    Issue("consecutive_assistant", i, "two assistant messages in a row")
                )

            content = msg.get("content")
            tool_calls = _tool_call_ids(msg)

            # R9 empty no-op turn
            content_is_empty = content is None or (
                isinstance(content, str) and content.strip() == ""
            )
            if content_is_empty and not tool_calls:
                errors.append(
                    Issue(
                        "empty_content_non_tool_call",
                        i,
                        "assistant turn has no content and no tool_calls",
                    )
                )

            # If a previous assistant had open tool_calls and we hit another
            # assistant before all replies arrived, that's R7 (unanswered).
            if pending_tool_call_ids:
                errors.append(
                    Issue(
                        "unanswered_tool_call",
                        pending_tool_call_assistant_idx if pending_tool_call_assistant_idx is not None else i,
                        f"assistant declared tool_calls {pending_tool_call_ids!r} "
                        "but next assistant turn arrived before tool replies",
                    )
                )
                pending_tool_call_ids = []
                pending_tool_call_assistant_idx = None

            # Open new pending set if this assistant declared tool_calls.
            if tool_calls:
                pending_tool_call_ids = list(tool_calls)
                pending_tool_call_assistant_idx = i

        elif role == "user":
            # R5 consecutive user
            if i > 0 and _role(msgs[i - 1]) == "user":
                errors.append(
                    Issue("consecutive_user", i, "two user messages in a row")
                )
            # If we still had open tool_calls and a user message arrives, those
            # tool calls were never answered — R7.
            if pending_tool_call_ids:
                errors.append(
                    Issue(
                        "unanswered_tool_call",
                        pending_tool_call_assistant_idx if pending_tool_call_assistant_idx is not None else i,
                        f"assistant declared tool_calls {pending_tool_call_ids!r} "
                        "but next user turn arrived before tool replies",
                    )
                )
                pending_tool_call_ids = []
                pending_tool_call_assistant_idx = None

        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id:
                errors.append(
                    Issue(
                        "tool_without_call",
                        i,
                        "tool message missing tool_call_id",
                    )
                )
            elif tool_call_id not in pending_tool_call_ids:
                errors.append(
                    Issue(
                        "tool_without_call",
                        i,
                        f"tool message references id={tool_call_id!r} "
                        f"but no preceding assistant declared it (open ids: {pending_tool_call_ids!r})",
                    )
                )
            else:
                pending_tool_call_ids.remove(tool_call_id)
                if not pending_tool_call_ids:
                    pending_tool_call_assistant_idx = None

        # role == "system" handled above for R3.

    # End-of-list checks.
    if pending_tool_call_ids:
        # R10 — last assistant left open tool calls.
        last_idx = pending_tool_call_assistant_idx if pending_tool_call_assistant_idx is not None else len(msgs) - 1
        errors.append(
            Issue(
                "trailing_assistant_with_open_tool_calls",
                last_idx,
                f"conversation ended with unanswered tool_calls={pending_tool_call_ids!r}",
            )
        )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)
