#!/usr/bin/env python3
"""
Mixed-script confusable-character detector for LLM output.

Catches characters from non-Latin scripts (Cyrillic, Greek, fullwidth, etc.)
that visually resemble ASCII letters and silently sneak into otherwise-Latin
words. These are a common LLM artifact when the model has been trained on
multilingual data, and they are notorious for breaking:

  * code identifiers (e.g. `setTimeоut` with a Cyrillic 'о')
  * URLs and domain names (homograph attacks)
  * grep / search workflows
  * copy-pasted shell commands

We flag any token containing a Latin ASCII letter alongside a confusable
non-Latin letter from a curated map. Pure stdlib.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass

# Curated map: confusable codepoint -> (ASCII lookalike, script name).
# Kept small and high-precision rather than exhaustive; covers the most common
# offenders we see from large multilingual models.
CONFUSABLES: dict[str, tuple[str, str]] = {
    # Cyrillic lowercase that look like Latin lowercase
    "\u0430": ("a", "Cyrillic"),   # а
    "\u0435": ("e", "Cyrillic"),   # е
    "\u043e": ("o", "Cyrillic"),   # о
    "\u0440": ("p", "Cyrillic"),   # р
    "\u0441": ("c", "Cyrillic"),   # с
    "\u0445": ("x", "Cyrillic"),   # х
    "\u0443": ("y", "Cyrillic"),   # у
    "\u0456": ("i", "Cyrillic"),   # і
    "\u0458": ("j", "Cyrillic"),   # ј
    # Cyrillic uppercase
    "\u0410": ("A", "Cyrillic"),   # А
    "\u0415": ("E", "Cyrillic"),   # Е
    "\u041e": ("O", "Cyrillic"),   # О
    "\u0420": ("P", "Cyrillic"),   # Р
    "\u0421": ("C", "Cyrillic"),   # С
    "\u0425": ("X", "Cyrillic"),   # Х
    "\u041d": ("H", "Cyrillic"),   # Н
    "\u041a": ("K", "Cyrillic"),   # К
    "\u041c": ("M", "Cyrillic"),   # М
    "\u0422": ("T", "Cyrillic"),   # Т
    "\u0412": ("B", "Cyrillic"),   # В
    # Greek
    "\u03bf": ("o", "Greek"),      # ο
    "\u03b1": ("a", "Greek"),      # α
    "\u03c1": ("p", "Greek"),      # ρ
    "\u03b9": ("i", "Greek"),      # ι
    "\u0391": ("A", "Greek"),      # Α
    "\u0392": ("B", "Greek"),      # Β
    "\u0395": ("E", "Greek"),      # Ε
    "\u039f": ("O", "Greek"),      # Ο
    "\u03a1": ("P", "Greek"),      # Ρ
    "\u03a4": ("T", "Greek"),      # Τ
    # Fullwidth Latin (sometimes injected by CJK-tuned models)
    **{chr(0xFF21 + i): (chr(ord("A") + i), "Fullwidth") for i in range(26)},
    **{chr(0xFF41 + i): (chr(ord("a") + i), "Fullwidth") for i in range(26)},
}

ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
TOKEN_RE = re.compile(r"\S+")


@dataclass
class Hit:
    line_no: int
    col: int
    token: str
    char: str
    codepoint: str
    lookalike: str
    script: str
    name: str


def scan(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in TOKEN_RE.finditer(line):
            token = m.group(0)
            if not ASCII_LETTER_RE.search(token):
                # Pure non-Latin token (e.g. intentional Russian word) — skip;
                # only flag *mixed* tokens.
                continue
            for offset, ch in enumerate(token):
                if ch in CONFUSABLES:
                    look, script = CONFUSABLES[ch]
                    try:
                        name = unicodedata.name(ch)
                    except ValueError:
                        name = "<unnamed>"
                    hits.append(
                        Hit(
                            line_no=line_no,
                            col=m.start() + offset + 1,
                            token=token,
                            char=ch,
                            codepoint=f"U+{ord(ch):04X}",
                            lookalike=look,
                            script=script,
                            name=name,
                        )
                    )
    return hits


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] != "-":
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    hits = scan(text)
    for h in hits:
        print(
            f"line {h.line_no} col {h.col}: {h.script} {h.codepoint} "
            f"({h.name}) looks like ASCII '{h.lookalike}'"
        )
        print(f"  token: {h.token!r}")
    if hits:
        print(f"\nFAIL: {len(hits)} confusable character(s) in mixed-script tokens")
        return 1
    print("OK: no mixed-script confusables found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
