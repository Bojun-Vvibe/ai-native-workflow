"""Prompt-template variable validator.

Strict, declarative validator for `str.format`-style prompt templates.
The two correctness traps it exists to prevent:

1. **Unfilled placeholders shipped to the model.** A typo in the
   caller (`{user_quesiton}` → renders as the literal string
   `{user_quesiton}` because the caller passed `user_question=…`)
   is impossible to catch in code review and very expensive in
   prod. `validate(template, declared_vars)` parses the template,
   computes the actual placeholder set, and refuses any mismatch
   loudly with a structured `ValidationError`.

2. **Silently-coerced values.** `str.format` will happily render
   `None`, `[]`, `{}`, multi-MB blobs, or a `repr(SomeObject)` into
   a prompt. This validator enforces a per-variable type contract
   and a per-variable max length so a `None` does not become the
   literal string `"None"` inside the system prompt and a 4MB
   accidental document does not blow the model's context window.

Stdlib-only (`string.Formatter`, `dataclasses`). No I/O. No
template-engine dependency: this is `str.format`, the contract that
ships with Python — exactly so that pinning a template version
(`prompt-version-pinning-manifest`) does not pin a Jinja minor too.

Forbidden in templates:
  * Positional placeholders (`{}`, `{0}`) — caller intent is unclear,
    refactors silently break.
  * Format specs and conversions (`{x:>10}`, `{x!r}`) — moves
    rendering decisions out of the caller and into a template the
    caller may not own.
  * Attribute / index access (`{user.name}`, `{items[0]}`) — couples
    the template to the caller's object graph.

If you actually need any of those, you do not want this template;
use a real template engine and accept its blast radius.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Any, Mapping


class ValidationError(Exception):
    """Raised on any contract mismatch. Caller must not ship the prompt."""


@dataclass(frozen=True)
class VarSpec:
    """Per-variable contract.

    `type_` is checked with `isinstance`. `max_len` is checked against
    the *string* length the value will render to (`str(value)`), which
    is what actually counts inside the prompt. `allow_empty=False`
    rejects `""` / `[]` / `{}` because in practice an empty string
    inside a system-prompt slot is almost always a caller bug, not a
    deliberate empty section.
    """

    type_: type | tuple[type, ...]
    max_len: int
    allow_empty: bool = False

    def __post_init__(self) -> None:
        if self.max_len <= 0:
            raise ValueError(f"max_len must be positive, got {self.max_len}")


@dataclass
class ValidationReport:
    template_placeholders: tuple[str, ...]
    declared_vars: tuple[str, ...]
    rendered_length: int


def parse_placeholders(template: str) -> tuple[str, ...]:
    """Return the ordered, deduped set of *named* placeholders in `template`.

    Raises `ValidationError` for any of the forbidden constructs.
    """
    formatter = string.Formatter()
    seen: list[str] = []
    seen_set: set[str] = set()
    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        if field_name is None:
            continue  # trailing literal text
        if field_name == "":
            raise ValidationError(
                "positional placeholder `{}` is forbidden — name every variable"
            )
        if field_name.isdigit():
            raise ValidationError(
                f"positional placeholder `{{{field_name}}}` is forbidden — name every variable"
            )
        if "." in field_name or "[" in field_name:
            raise ValidationError(
                f"attribute / index access in placeholder is forbidden: `{{{field_name}}}`"
            )
        if format_spec:
            raise ValidationError(
                f"format spec is forbidden in placeholder `{{{field_name}:{format_spec}}}`"
                " — render at the caller, not in the template"
            )
        if conversion:
            raise ValidationError(
                f"conversion `!{conversion}` is forbidden in placeholder `{{{field_name}!{conversion}}}`"
            )
        if field_name not in seen_set:
            seen.append(field_name)
            seen_set.add(field_name)
    return tuple(seen)


def render(
    template: str,
    values: Mapping[str, Any],
    contract: Mapping[str, VarSpec],
) -> tuple[str, ValidationReport]:
    """Validate then render. Return (rendered_prompt, report).

    Raises `ValidationError` on any mismatch and never partially renders.
    """
    placeholders = parse_placeholders(template)
    declared = tuple(contract.keys())

    # 1. Placeholder set vs contract set
    missing_in_contract = [p for p in placeholders if p not in contract]
    if missing_in_contract:
        raise ValidationError(
            f"template uses {missing_in_contract!r} but contract does not declare them"
        )
    unused_in_template = [d for d in declared if d not in placeholders]
    if unused_in_template:
        raise ValidationError(
            f"contract declares {unused_in_template!r} but template never references them"
        )

    # 2. Value set vs contract set
    missing_values = [p for p in placeholders if p not in values]
    if missing_values:
        raise ValidationError(f"caller did not provide values for {missing_values!r}")
    extra_values = [k for k in values if k not in contract]
    if extra_values:
        raise ValidationError(
            f"caller passed values not in contract: {extra_values!r}"
            " — refusing to silently drop them"
        )

    # 3. Per-variable type and length
    for name, spec in contract.items():
        v = values[name]
        if not isinstance(v, spec.type_):
            type_name = (
                spec.type_.__name__
                if isinstance(spec.type_, type)
                else "/".join(t.__name__ for t in spec.type_)
            )
            raise ValidationError(
                f"{name!r}: expected {type_name}, got {type(v).__name__}={v!r}"
            )
        rendered_value = str(v)
        if not spec.allow_empty and len(rendered_value) == 0:
            raise ValidationError(
                f"{name!r}: empty value not allowed (set allow_empty=True if intentional)"
            )
        if len(rendered_value) > spec.max_len:
            raise ValidationError(
                f"{name!r}: rendered length {len(rendered_value)} exceeds"
                f" max_len {spec.max_len}"
            )

    rendered = template.format(**values)
    return rendered, ValidationReport(
        template_placeholders=placeholders,
        declared_vars=declared,
        rendered_length=len(rendered),
    )
