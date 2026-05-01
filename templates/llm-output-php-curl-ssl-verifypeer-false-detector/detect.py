#!/usr/bin/env python3
"""
llm-output-php-curl-ssl-verifypeer-false-detector

Flags PHP source where libcurl TLS certificate verification is
disabled via ``curl_setopt`` / ``curl_setopt_array`` setting one of:

* ``CURLOPT_SSL_VERIFYPEER`` to a falsy value (``false``, ``0``,
  ``"0"``, ``null``, ``FALSE``, ``False``)
* ``CURLOPT_SSL_VERIFYHOST`` to ``0`` / ``false`` (1 is also wrong
  but flagged separately as a weak-but-not-zero pattern; we only
  flag the fully-disabled values here)

This is the canonical CWE-295 / CWE-297 (Improper Certificate
Validation) shape in PHP. Under "make this HTTPS request work in
dev" pressure an LLM tends to write::

    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);

instead of fixing the actual CA bundle / hostname mismatch.

The detector handles both call shapes:

1. **php-curl-verifypeer-false** — direct
   ``curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, <falsy>)``.
2. **php-curl-verifyhost-zero** — direct
   ``curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0|false)``.
3. **php-curl-setopt-array-verifypeer-false** — same options inside
   a ``curl_setopt_array($ch, [ ... ])`` array literal.

Suppress with a trailing ``// llm-allow:php-curl-tls`` or
``# llm-allow:php-curl-tls`` on the relevant ``curl_setopt`` line
(or anywhere within the same statement / array literal).

Stdlib only. Reads files passed on argv (or recurses into directories
for ``*.php``, ``*.phtml``, ``*.md``, ``*.markdown``). Exit code 1 if
any findings, 0 otherwise, 2 on usage error.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, List, Tuple

SUPPRESS = "llm-allow:php-curl-tls"

SCAN_SUFFIXES = (".php", ".phtml", ".md", ".markdown")


# ---------------------------------------------------------------------------
# Markdown fence extraction. We pull php-tagged fences out of markdown
# and feed their bodies through the same analyzer.
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(
    r"^([ \t]{0,3})(```+|~~~+)[ \t]*([A-Za-z0-9_+\-.]*)[^\n]*\n(.*?)(?:^\1\2[ \t]*$)",
    re.DOTALL | re.MULTILINE,
)
_PHP_LANGS = {"php", "phtml", "php5", "php7", "php8"}


def _iter_php_blocks(text: str) -> Iterable[Tuple[str, int]]:
    for m in _FENCE_RE.finditer(text):
        lang = (m.group(3) or "").strip().lower()
        if lang in _PHP_LANGS:
            body_start = m.start(4)
            line_offset = text.count("\n", 0, body_start)
            yield m.group(4), line_offset


# ---------------------------------------------------------------------------
# Comment masking. PHP supports //, #, and /* */. Replace bodies with
# spaces so line numbers stay stable, but keep the SUPPRESS marker
# detectable by also retaining the raw line text in a parallel buffer.
# ---------------------------------------------------------------------------
def _mask_comments(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    in_str = None  # None | '"' | "'"
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_str is not None:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            if j < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
            continue
        if c == "#":
            # # is a line comment in PHP only outside of strings; we
            # are outside a string here.
            j = text.find("\n", i)
            if j < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (j - i))
                i = j
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                seg = text[i:]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = n
            else:
                seg = text[i : j + 2]
                out.append("".join(" " if ch != "\n" else "\n" for ch in seg))
                i = j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Falsy-value classifier for the third arg of curl_setopt.
# ---------------------------------------------------------------------------
_FALSY_RE = re.compile(
    r"""^\s*(
        false | FALSE | False
      | null  | NULL  | Null
      | 0
      | "0" | '0'
      | "false" | 'false'
    )\s*$""",
    re.VERBOSE,
)

_ZERO_RE = re.compile(
    r"""^\s*(
        false | FALSE | False
      | 0
      | "0" | '0'
    )\s*$""",
    re.VERBOSE,
)


def _is_falsy(expr: str) -> bool:
    return bool(_FALSY_RE.match(expr))


def _is_zero(expr: str) -> bool:
    return bool(_ZERO_RE.match(expr))


# ---------------------------------------------------------------------------
# Find balanced argument span starting at index of '(' or '['.
# ---------------------------------------------------------------------------
def _balanced_end(text: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level(text: str, sep: str) -> List[str]:
    """Split text on `sep` at paren/bracket depth 0."""
    out: List[str] = []
    depth_p = 0
    depth_b = 0
    depth_c = 0
    cur_start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth_p += 1
        elif c == ")":
            depth_p -= 1
        elif c == "[":
            depth_b += 1
        elif c == "]":
            depth_b -= 1
        elif c == "{":
            depth_c += 1
        elif c == "}":
            depth_c -= 1
        elif c == sep and depth_p == 0 and depth_b == 0 and depth_c == 0:
            out.append(text[cur_start:i])
            cur_start = i + 1
        i += 1
    out.append(text[cur_start:])
    return out


# ---------------------------------------------------------------------------
# Detector core.
# ---------------------------------------------------------------------------
_SETOPT_RE = re.compile(r"\bcurl_setopt\s*\(")
_SETOPT_ARRAY_RE = re.compile(r"\bcurl_setopt_array\s*\(")

# Inside an array literal we need to find  KEY => VALUE  pairs at
# depth 0. We capture pairs by splitting on top-level commas, then
# splitting each pair on top-level "=>".
_FATARROW_RE = re.compile(r"=>")

_VERIFYPEER_TOK = "CURLOPT_SSL_VERIFYPEER"
_VERIFYHOST_TOK = "CURLOPT_SSL_VERIFYHOST"


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _statement_end(text: str, start: int) -> int:
    """Return index just after the next ';' at depth 0 from start."""
    depth_p = 0
    depth_b = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "(":
            depth_p += 1
        elif c == ")":
            depth_p -= 1
        elif c == "[":
            depth_b += 1
        elif c == "]":
            depth_b -= 1
        elif c == ";" and depth_p == 0 and depth_b == 0:
            return i + 1
        i += 1
    return n


def _has_suppress(raw: str, span_start: int, span_end: int) -> bool:
    # Extend the search window to the end of the line containing
    # span_end, so a trailing "// llm-allow:..." after the ';' still
    # counts as suppressing the same statement.
    eol = raw.find("\n", span_end)
    if eol < 0:
        eol = len(raw)
    return SUPPRESS in raw[span_start:eol]


def _scan_block(
    raw: str,
    masked: str,
    line_offset: int,
    findings: List[Tuple[int, str, str, str]],
) -> None:
    # 1. curl_setopt($ch, CURLOPT_..., <value>)
    for m in _SETOPT_RE.finditer(masked):
        open_paren = m.end() - 1
        close_paren = _balanced_end(masked, open_paren, "(", ")")
        if close_paren < 0:
            continue
        inner = masked[open_paren + 1 : close_paren]
        parts = _split_top_level(inner, ",")
        if len(parts) < 3:
            continue
        opt = parts[1].strip()
        val = parts[2]
        stmt_end = _statement_end(masked, close_paren + 1)
        if _has_suppress(raw, m.start(), stmt_end):
            continue
        # match the option token itself; allow leading namespace, e.g.
        # \CURLOPT_SSL_VERIFYPEER
        opt_clean = opt.lstrip("\\").strip()
        if opt_clean == _VERIFYPEER_TOK and _is_falsy(val):
            line = _line_of(raw, m.start()) + line_offset
            snippet = raw[m.start() : min(stmt_end, m.start() + 160)].splitlines()[0]
            findings.append(
                (
                    line,
                    "php-curl-verifypeer-false",
                    "CURLOPT_SSL_VERIFYPEER set to a falsy value disables TLS certificate validation (CWE-295)",
                    snippet,
                )
            )
        elif opt_clean == _VERIFYHOST_TOK and _is_zero(val):
            line = _line_of(raw, m.start()) + line_offset
            snippet = raw[m.start() : min(stmt_end, m.start() + 160)].splitlines()[0]
            findings.append(
                (
                    line,
                    "php-curl-verifyhost-zero",
                    "CURLOPT_SSL_VERIFYHOST set to 0/false disables hostname check (CWE-297)",
                    snippet,
                )
            )

    # 2. curl_setopt_array($ch, [ ... ])
    for m in _SETOPT_ARRAY_RE.finditer(masked):
        open_paren = m.end() - 1
        close_paren = _balanced_end(masked, open_paren, "(", ")")
        if close_paren < 0:
            continue
        inner = masked[open_paren + 1 : close_paren]
        # find first array literal — either [ ... ] or array( ... )
        # we scan inner for the first '[' at depth 0 (ignoring the
        # leading $ch, comma).
        bracket_idx = -1
        depth_p = 0
        for k, c in enumerate(inner):
            if c == "(":
                depth_p += 1
            elif c == ")":
                depth_p -= 1
            elif c == "[" and depth_p == 0:
                bracket_idx = k
                break
        if bracket_idx < 0:
            continue
        # absolute index in masked
        abs_open = open_paren + 1 + bracket_idx
        abs_close = _balanced_end(masked, abs_open, "[", "]")
        if abs_close < 0:
            continue
        body = masked[abs_open + 1 : abs_close]
        stmt_end = _statement_end(masked, close_paren + 1)
        if _has_suppress(raw, m.start(), stmt_end):
            continue
        for pair in _split_top_level(body, ","):
            if "=>" not in pair:
                continue
            key_part, _, val_part = pair.partition("=>")
            key = key_part.strip().lstrip("\\").strip()
            val = val_part
            if key == _VERIFYPEER_TOK and _is_falsy(val):
                # locate this pair's line for a useful number
                pair_off = body.find(pair)
                pair_abs = abs_open + 1 + pair_off if pair_off >= 0 else m.start()
                line = _line_of(raw, pair_abs) + line_offset
                snippet = raw[pair_abs : pair_abs + 160].splitlines()[0]
                findings.append(
                    (
                        line,
                        "php-curl-setopt-array-verifypeer-false",
                        "CURLOPT_SSL_VERIFYPEER => falsy in curl_setopt_array disables TLS validation (CWE-295)",
                        snippet,
                    )
                )
            elif key == _VERIFYHOST_TOK and _is_zero(val):
                pair_off = body.find(pair)
                pair_abs = abs_open + 1 + pair_off if pair_off >= 0 else m.start()
                line = _line_of(raw, pair_abs) + line_offset
                snippet = raw[pair_abs : pair_abs + 160].splitlines()[0]
                findings.append(
                    (
                        line,
                        "php-curl-setopt-array-verifyhost-zero",
                        "CURLOPT_SSL_VERIFYHOST => 0/false in curl_setopt_array disables hostname check (CWE-297)",
                        snippet,
                    )
                )


# ---------------------------------------------------------------------------
# File / dir driver.
# ---------------------------------------------------------------------------
def scan_text(text: str) -> List[Tuple[int, str, str, str]]:
    findings: List[Tuple[int, str, str, str]] = []
    masked = _mask_comments(text)
    _scan_block(text, masked, 0, findings)
    # also extract php fences from markdown-ish content
    for body, off in _iter_php_blocks(text):
        masked_body = _mask_comments(body)
        _scan_block(body, masked_body, off, findings)
    findings.sort(key=lambda x: x[0])
    return findings


def scan_path(path: str) -> List[Tuple[str, int, str, str, str]]:
    out: List[Tuple[str, int, str, str, str]] = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name.endswith(SCAN_SUFFIXES):
                    full = os.path.join(root, name)
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as fh:
                            text = fh.read()
                    except OSError:
                        continue
                    for f in scan_text(text):
                        out.append((full, *f))
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return out
    for f in scan_text(text):
        out.append((path, *f))
    return out


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: detect.py PATH [PATH ...]\n"
            "  Scans PHP / Markdown for curl_setopt() calls that disable TLS\n"
            "  certificate validation (CURLOPT_SSL_VERIFYPEER=false,\n"
            "  CURLOPT_SSL_VERIFYHOST=0).",
            file=sys.stderr,
        )
        return 2
    any_finding = False
    for path in argv[1:]:
        for fpath, line, code, msg, snip in scan_path(path):
            any_finding = True
            print(f"{fpath}:{line}: {code}: {msg}: {snip}")
    return 1 if any_finding else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
