#!/usr/bin/env python3
"""
Emoji variation-selector detector for LLM output.

Detects two related bug classes around U+FE0F (VARIATION SELECTOR-16,
the "emoji presentation" selector):

  1. **missing_vs16**: a base codepoint that has both text-style and
     emoji-style presentations (e.g. U+2764 HEAVY BLACK HEART, U+2600
     BLACK SUN WITH RAYS, U+260E BLACK TELEPHONE, U+2702 BLACK
     SCISSORS) appears WITHOUT a trailing U+FE0F. Many platforms
     render these as monochrome dingbats unless VS16 is appended,
     which silently downgrades user-facing output.

  2. **stray_vs15**: U+FE0E (VARIATION SELECTOR-15, "text
     presentation") appears after a fully-qualified emoji that the
     author almost certainly meant to render in color. This is a
     less-common artifact but it forces text-style rendering on the
     next codepoint.

  3. **vs16_after_non_base**: U+FE0F appears after a codepoint that
     has no defined emoji/text variation. The selector is wasted and
     the byte stream is one codepoint heavier than it needs to be.

Pure stdlib. The base-emoji set is a curated, conservative list of
the most common offenders LLMs emit unqualified — it is not the full
Unicode emoji-variation-sequences table, on purpose, to keep the
false-positive rate low.
"""
from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass


VS15 = "\uFE0E"  # text presentation
VS16 = "\uFE0F"  # emoji presentation

# Curated set of base codepoints that are commonly emitted unqualified
# by LLMs and that visibly render differently with vs without VS16 on
# mainstream platforms (iOS, Android, Windows, web fonts).
BASE_NEEDS_VS16: dict[str, str] = {
    "\u2600": "BLACK SUN WITH RAYS",
    "\u2601": "CLOUD",
    "\u2614": "UMBRELLA WITH RAIN DROPS",
    "\u2615": "HOT BEVERAGE",
    "\u261D": "WHITE UP POINTING INDEX",
    "\u263A": "WHITE SMILING FACE",
    "\u2648": "ARIES",
    "\u2660": "BLACK SPADE SUIT",
    "\u2663": "BLACK CLUB SUIT",
    "\u2665": "BLACK HEART SUIT",
    "\u2666": "BLACK DIAMOND SUIT",
    "\u2668": "HOT SPRINGS",
    "\u2693": "ANCHOR",
    "\u26A0": "WARNING SIGN",
    "\u26A1": "HIGH VOLTAGE SIGN",
    "\u26BD": "SOCCER BALL",
    "\u26BE": "BASEBALL",
    "\u26C4": "SNOWMAN WITHOUT SNOW",
    "\u26C5": "SUN BEHIND CLOUD",
    "\u26D4": "NO ENTRY",
    "\u26EA": "CHURCH",
    "\u26F2": "FOUNTAIN",
    "\u26F3": "FLAG IN HOLE",
    "\u26F5": "SAILBOAT",
    "\u26FA": "TENT",
    "\u26FD": "FUEL PUMP",
    "\u2702": "BLACK SCISSORS",
    "\u2705": "WHITE HEAVY CHECK MARK",
    "\u2708": "AIRPLANE",
    "\u2709": "ENVELOPE",
    "\u270A": "RAISED FIST",
    "\u270B": "RAISED HAND",
    "\u270C": "VICTORY HAND",
    "\u270F": "PENCIL",
    "\u2712": "BLACK NIB",
    "\u2714": "HEAVY CHECK MARK",
    "\u2716": "HEAVY MULTIPLICATION X",
    "\u271D": "LATIN CROSS",
    "\u2721": "STAR OF DAVID",
    "\u2728": "SPARKLES",
    "\u2733": "EIGHT SPOKED ASTERISK",
    "\u2734": "EIGHT POINTED BLACK STAR",
    "\u2744": "SNOWFLAKE",
    "\u2747": "SPARKLE",
    "\u274C": "CROSS MARK",
    "\u274E": "NEGATIVE SQUARED CROSS MARK",
    "\u2753": "BLACK QUESTION MARK ORNAMENT",
    "\u2757": "HEAVY EXCLAMATION MARK SYMBOL",
    "\u2764": "HEAVY BLACK HEART",
    "\u27A1": "BLACK RIGHTWARDS ARROW",
    "\u2934": "ARROW POINTING RIGHTWARDS THEN CURVING UPWARDS",
    "\u2935": "ARROW POINTING RIGHTWARDS THEN CURVING DOWNWARDS",
    "\u2B05": "LEFTWARDS BLACK ARROW",
    "\u2B06": "UPWARDS BLACK ARROW",
    "\u2B07": "DOWNWARDS BLACK ARROW",
    "\u2B1B": "BLACK LARGE SQUARE",
    "\u2B1C": "WHITE LARGE SQUARE",
    "\u2B50": "WHITE MEDIUM STAR",
    "\u2B55": "HEAVY LARGE CIRCLE",
    "\u260E": "BLACK TELEPHONE",
    "\u2611": "BALLOT BOX WITH CHECK",
    "\u2618": "SHAMROCK",
    "\u261D": "WHITE UP POINTING INDEX",
    "\u2622": "RADIOACTIVE SIGN",
    "\u2623": "BIOHAZARD SIGN",
    "\u2626": "ORTHODOX CROSS",
    "\u262A": "STAR AND CRESCENT",
    "\u262E": "PEACE SYMBOL",
    "\u262F": "YIN YANG",
    "\u2638": "WHEEL OF DHARMA",
    "\u2639": "WHITE FROWNING FACE",
    "\u2692": "HAMMER AND PICK",
    "\u2694": "CROSSED SWORDS",
    "\u2695": "STAFF OF AESCULAPIUS",
    "\u2696": "SCALES",
    "\u2697": "ALEMBIC",
    "\u2699": "GEAR",
    "\u269B": "ATOM SYMBOL",
    "\u269C": "FLEUR-DE-LIS",
    "\u26A7": "MALE WITH STROKE AND MALE AND FEMALE SIGN",
    "\u26B0": "COFFIN",
    "\u26B1": "FUNERAL URN",
    "\u26C8": "THUNDER CLOUD AND RAIN",
    "\u26CF": "PICK",
    "\u26D1": "HELMET WITH WHITE CROSS",
    "\u26D3": "CHAINS",
    "\u26E9": "SHINTO SHRINE",
    "\u26F0": "MOUNTAIN",
    "\u26F1": "UMBRELLA ON GROUND",
    "\u26F4": "FERRY",
    "\u26F7": "SKIER",
    "\u26F8": "ICE SKATE",
    "\u26F9": "PERSON WITH BALL",
    "\u2733": "EIGHT SPOKED ASTERISK",
    "\u2763": "HEAVY HEART EXCLAMATION MARK ORNAMENT",
    "\u3030": "WAVY DASH",
    "\u303D": "PART ALTERNATION MARK",
    "\u3297": "CIRCLED IDEOGRAPH CONGRATULATION",
    "\u3299": "CIRCLED IDEOGRAPH SECRET",
}


@dataclass
class Hit:
    line_no: int
    col: int
    kind: str
    codepoint: str
    name: str
    detail: str


def _name(ch: str) -> str:
    try:
        return unicodedata.name(ch)
    except ValueError:
        return "<unnamed>"


def _is_emoji_codepoint(ch: str) -> bool:
    """Heuristic: a codepoint we treat as a 'fully-qualified emoji
    base' that should NOT be followed by VS15 (text presentation).
    Covers the main Unicode emoji blocks + the curated dual-use set."""
    cp = ord(ch)
    if (
        0x1F300 <= cp <= 0x1FAFF       # main emoji blocks
        or 0x1F000 <= cp <= 0x1F2FF
        or 0x2700 <= cp <= 0x27BF      # Dingbats
        or ch in BASE_NEEDS_VS16
    ):
        return True
    return False


def scan(text: str) -> list[Hit]:
    hits: list[Hit] = []
    line_no = 1
    col = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line_no += 1
            col = 0
            i += 1
            continue
        col += 1
        nxt = text[i + 1] if i + 1 < n else ""

        if ch in BASE_NEEDS_VS16 and nxt != VS16:
            # Allow if the base is followed by a skin-tone modifier or ZWJ
            # — those sequences also carry implicit emoji presentation.
            if not (nxt and (0x1F3FB <= ord(nxt) <= 0x1F3FF or nxt == "\u200D")):
                hits.append(
                    Hit(
                        line_no=line_no,
                        col=col,
                        kind="missing_vs16",
                        codepoint=f"U+{ord(ch):04X}",
                        name=_name(ch),
                        detail=(
                            "base emoji rendered without VS16; many platforms "
                            "will display the monochrome text dingbat instead "
                            "of the color emoji"
                        ),
                    )
                )

        if ch == VS15:
            prev = text[i - 1] if i > 0 else ""
            if prev and _is_emoji_codepoint(prev):
                hits.append(
                    Hit(
                        line_no=line_no,
                        col=col,
                        kind="stray_vs15",
                        codepoint="U+FE0E",
                        name="VARIATION SELECTOR-15",
                        detail=(
                            f"text-presentation selector after emoji "
                            f"U+{ord(prev):04X}; forces monochrome rendering"
                        ),
                    )
                )

        if ch == VS16:
            prev = text[i - 1] if i > 0 else ""
            if not prev or (
                prev not in BASE_NEEDS_VS16 and not _is_emoji_codepoint(prev)
            ):
                hits.append(
                    Hit(
                        line_no=line_no,
                        col=col,
                        kind="vs16_after_non_base",
                        codepoint="U+FE0F",
                        name="VARIATION SELECTOR-16",
                        detail=(
                            "VS16 after non-emoji-base "
                            f"U+{ord(prev):04X}; wasted bytes"
                            if prev else "VS16 at start of input; wasted bytes"
                        ),
                    )
                )

        i += 1
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
            f"line {h.line_no} col {h.col}: {h.kind} {h.codepoint} "
            f"({h.name})"
        )
        print(f"  {h.detail}")
    if hits:
        print(f"\nFAIL: {len(hits)} variation-selector finding(s)")
        return 1
    print("OK: no variation-selector issues found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
