"""
Worked example: llm-streaming-chunk-boundary-validator

Six recorded chunk sequences — clean baselines for each mode plus one
case for each finding class — proving the validator catches the four
boundary-class bugs that silently corrupt a streaming consumer.

Run:
    python3 example.py
"""

from __future__ import annotations

import json

from validator import validate


def banner(title: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)


# ---------------------------------------------------------------------
# 01 — clean text stream. ASCII split on word boundaries; no findings.
# ---------------------------------------------------------------------
clean_text = [b"The quick ", b"brown fox ", b"jumps over."]

# ---------------------------------------------------------------------
# 02 — utf8_split. The character "你" is U+4F60 → 0xE4 0xBD 0xA0 (3 bytes).
# Split it after the leader byte; the next chunk carries the trailing two.
# ---------------------------------------------------------------------
utf8_bad = [b"hello \xe4", b"\xbd\xa0 world"]   # "你" sliced 1+2

# ---------------------------------------------------------------------
# 03 — codepoint_grapheme. Family emoji 👨‍👩‍👧 = man ZWJ woman ZWJ girl.
# Split *at* the ZWJ — terminal renders three separate emoji for one tick.
# ---------------------------------------------------------------------
zwj_bad = [
    "👨".encode("utf-8") + b"\xe2\x80\x8d",      # man + ZWJ
    "👩".encode("utf-8") + b"\xe2\x80\x8d" + "👧".encode("utf-8"),
]

# ---------------------------------------------------------------------
# 04 — clean JSON stream. Splits between top-level keys and on whitespace.
# ---------------------------------------------------------------------
clean_json = [
    b'{"verdict":"approve",',
    b'"score":0.97,',
    b'"reason":"all checks passed"}',
]

# ---------------------------------------------------------------------
# 05 — inside_string. Split lands inside the value of "reason".
# ---------------------------------------------------------------------
inside_str_bad = [
    b'{"verdict":"approve","reason":"all chec',
    b'ks passed"}',
]

# ---------------------------------------------------------------------
# 06 — escape_split. Split lands *between* a `\` and its escapee `n`.
# A naive line-buffered consumer may emit a literal backslash before the
# `n` arrives, then a literal `n`, instead of the intended newline.
# ---------------------------------------------------------------------
escape_bad = [
    b'{"msg":"line-1\\',
    b'nline-2"}',
]

cases: list[tuple[str, list[bytes], str]] = [
    ("01 clean text",           clean_text,     "text"),
    ("02 utf8_split",           utf8_bad,       "text"),
    ("03 codepoint_grapheme",   zwj_bad,        "text"),
    ("04 clean json",           clean_json,     "json"),
    ("05 inside_string",        inside_str_bad, "json"),
    ("06 escape_split",         escape_bad,     "json"),
]

for label, chunks, mode in cases:
    banner(f"{label}  (mode={mode})")
    rep = validate(chunks, mode=mode)
    print(json.dumps(rep.to_dict(), indent=2, sort_keys=True))
    print()

# Aggregate tally
banner("summary")
totals: dict[str, int] = {}
for label, chunks, mode in cases:
    rep = validate(chunks, mode=mode)
    for f in rep.findings:
        totals[f.kind] = totals.get(f.kind, 0) + 1
print(json.dumps({"finding_kind_totals": dict(sorted(totals.items()))}, indent=2))
