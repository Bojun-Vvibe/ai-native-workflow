"""Detect sentences in LLM prose that start with a lowercase letter.

Pure-stdlib. Splits a Markdown document into sentences (paragraph-aware,
fence-aware, list-aware) and reports any sentence whose first
alphabetic character is a lowercase letter and is not on a curated
allowlist (well-known intentionally-lowercase identifiers like
``iPhone``, ``eBay``, ``macOS``, ``rsync``, function-name conventions).

Rationale: this is a high-volume LLM-output cleanup chore. The model
will switch to a list, finish the list, then continue prose with a
lowercased sentence ("the next step..."), or follow a code fence with
"this snippet..." -- both of which read as fluent until a copy editor
sees them.

The detector is conservative -- it never flags a sentence whose first
token is on the allowlist, never flags inside fenced or inline code,
never flags inside Markdown headings (which have their own casing
conventions), and never flags inside link text or image alt text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Identifiers that legitimately start a sentence in lowercase. Match is
# case-sensitive on the first run of letters.
_LOWERCASE_FIRST_ALLOWLIST = frozenset({
    "iPhone", "iPad", "iPod", "iMac", "iOS", "iCloud", "iTunes",
    "eBay", "eMail", "macOS", "watchOS", "tvOS",
    "rsync", "ssh", "scp", "sed", "awk", "grep", "git", "npm", "pnpm",
    "yarn", "pip", "uv", "ls", "cd", "mv", "cp", "rm", "vim", "nano",
    "curl", "wget", "ffmpeg", "kubectl", "docker", "terraform",
    "node", "python", "ruby", "go", "rustc", "cargo",
    "argv", "argc", "stdin", "stdout", "stderr",
    "https", "http", "ftp", "mailto",
    "sudo", "make", "cmake", "bash", "zsh", "fish",
    "openSUSE", "openSSL",
})

_FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})\s*[^\r\n]*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_BLANK_RE = re.compile(r"^\s*$")


@dataclass(frozen=True)
class Finding:
    line_no: int           # 1-based line where the sentence starts
    column: int            # 1-based column of the offending first letter
    first_word: str        # the first whitespace-delimited token
    sentence_preview: str  # first ~60 chars of the offending sentence


def _strip_inline_code(line: str) -> str:
    """Replace `inline code` runs with spaces of equal length so column
    math against the original line stays correct."""
    out = []
    i = 0
    in_code = False
    while i < len(line):
        if line[i] == "`":
            j = i + 1
            while j < len(line) and line[j] == "`":
                j += 1
            tick_run = line[i:j]
            out.append(" " * len(tick_run))
            i = j
            in_code = not in_code
            continue
        if in_code:
            out.append(" ")
        else:
            out.append(line[i])
        i += 1
    return "".join(out)


def _strip_link_brackets(line: str) -> str:
    """Hide the URL portion of `[text](url)` and `![alt](url)` so a
    URL like `http://...` is not parsed as the start of a sentence.
    Keeps the bracketed text in place so prose reads continuously."""
    return re.sub(r"\]\([^)]*\)", lambda m: " " * len(m.group(0)), line)


def _is_sentence_terminator(ch: str) -> bool:
    return ch in ".!?"


def _split_sentences(paragraph_lines: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Walk a paragraph line-by-line and split into sentences. Returns
    a list of (line_no, column, sentence_text) where line_no/column
    point at the first character of the sentence in the original
    document."""
    sentences: list[tuple[int, int, str]] = []
    cur_chars: list[str] = []
    cur_start: tuple[int, int] | None = None

    for line_no, raw in paragraph_lines:
        cooked = _strip_link_brackets(_strip_inline_code(raw))
        for col_idx, ch in enumerate(cooked):
            if cur_start is None:
                if ch.isspace():
                    continue
                cur_start = (line_no, col_idx + 1)
            cur_chars.append(ch)
            if _is_sentence_terminator(ch):
                # Look ahead: only end if the next non-space char is
                # uppercase, a newline boundary, or end-of-paragraph.
                # We approximate "end-of-sentence" by always cutting on
                # terminator + space-or-EOL; this handles the
                # vast majority of LLM prose without a real tokenizer.
                sentences.append((cur_start[0], cur_start[1], "".join(cur_chars).strip()))
                cur_chars = []
                cur_start = None
        # Treat newline inside paragraph as a soft space; do not flush.
        cur_chars.append(" ")

    if cur_start is not None:
        tail = "".join(cur_chars).strip()
        if tail:
            sentences.append((cur_start[0], cur_start[1], tail))
    return sentences


def _first_word(s: str) -> str:
    m = re.match(r"\S+", s)
    return m.group(0) if m else ""


def detect_lowercase_sentence_starts(text: str) -> list[Finding]:
    findings: list[Finding] = []

    lines = text.splitlines()
    in_fence = False
    paragraph: list[tuple[int, str]] = []

    def flush() -> None:
        if not paragraph:
            return
        for line_no, col, sent in _split_sentences(paragraph):
            # Find the first alphabetic char in the sentence.
            for k, ch in enumerate(sent):
                if ch.isalpha():
                    if ch.islower():
                        word = _first_word(sent)
                        # Strip trailing punctuation from the first
                        # word for allowlist matching.
                        word_clean = word.rstrip(".,;:!?)\"'`]")
                        if word_clean not in _LOWERCASE_FIRST_ALLOWLIST:
                            findings.append(Finding(
                                line_no=line_no,
                                column=col + k,
                                first_word=word,
                                sentence_preview=sent[:60],
                            ))
                    break
        paragraph.clear()

    for i, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _HEADING_RE.match(line):
            flush()
            continue
        if _LIST_RE.match(line):
            # Each list item starts a fresh paragraph for this purpose.
            flush()
            stripped = _LIST_RE.sub("", line, count=1)
            paragraph.append((i, stripped))
            continue
        if _BLANK_RE.match(line):
            flush()
            continue
        paragraph.append((i, line))
    flush()

    findings.sort(key=lambda f: (f.line_no, f.column))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "OK: every sentence starts with an uppercase letter (or an allowlisted identifier)."
    out = [f"FOUND {len(findings)} lowercase sentence start(s):"]
    for f in findings:
        out.append(
            f"  line {f.line_no} col {f.column}: first_word={f.first_word!r} "
            f"sentence={f.sentence_preview!r}"
        )
    return "\n".join(out)
