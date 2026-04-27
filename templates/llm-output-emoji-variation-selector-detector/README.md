# llm-output-emoji-variation-selector-detector

Pure-stdlib detector for U+FE0F / U+FE0E variation-selector misuse in
LLM-generated text. The bug class where the output **looks fine in
the editor** but renders inconsistently across iOS, Android, Windows,
and the web because the byte stream is missing the emoji-presentation
selector.

## Why this exists

LLMs routinely emit "dual-use" base codepoints — the dingbats and
miscellaneous symbols block (U+2600..U+27BF) — without the trailing
U+FE0F that promotes them to color emoji presentation. The same
glyph then renders:

- **iOS Messages**: monochrome text dingbat (looks like a wingding)
- **Android Gboard**: color emoji
- **Slack / web**: depends on the font stack, often text-style
- **Email clients**: almost always text-style

So the operator ships what they think is a friendly ✈️ in a release
note and half their users see a stark black ✈ from the system font.
Worse, the bytes round-trip through copy-paste unchanged, so the
"fix" of pasting the same emoji back in does nothing.

The reverse bug — U+FE0E (VS15) appended to a fully-qualified emoji
— forces text-style rendering on a codepoint the author wanted in
color. Less common, equally invisible.

The third bug — U+FE0F appended to a codepoint that has no
text/emoji variation defined — is harmless visually but wastes
3 bytes per occurrence and trips strict Unicode validators.

## Detected kinds

| Kind | Trigger | Severity |
|---|---|---|
| `missing_vs16` | A base codepoint from the curated dual-use set is not followed by VS16, a skin-tone modifier, or a ZWJ | high — visible cross-platform inconsistency |
| `stray_vs15` | U+FE0E appears after a base we recognize as an emoji | high — forces unwanted monochrome rendering |
| `vs16_after_non_base` | U+FE0F appears after a codepoint with no defined emoji variation | low — wasted bytes only |

The base-emoji set is **deliberately curated** (~85 entries) rather
than the full Unicode emoji-variation-sequences table, to keep
false positives low on prose that legitimately uses dingbats as
text symbols (e.g. mathematical sparkles, technical writing about
Unicode itself).

## How to run

```bash
python3 detector.py example/bad.md   # exit 1, prints findings
python3 detector.py example/good.md  # exit 0
python3 detector.py -                 # read stdin
```

Stdlib only. Python 3.8+.

## Example output

`example/bad.md` exercises all three kinds. Verbatim run:

```
$ python3 detector.py example/bad.md
line 3 col 43: missing_vs16 U+2600 (BLACK SUN WITH RAYS)
  base emoji rendered without VS16; many platforms will display the monochrome text dingbat instead of the color emoji
line 4 col 23: missing_vs16 U+26A0 (WARNING SIGN)
  base emoji rendered without VS16; many platforms will display the monochrome text dingbat instead of the color emoji
line 6 col 24: missing_vs16 U+2708 (AIRPLANE)
  base emoji rendered without VS16; many platforms will display the monochrome text dingbat instead of the color emoji
line 7 col 61: missing_vs16 U+2764 (HEAVY BLACK HEART)
  base emoji rendered without VS16; many platforms will display the monochrome text dingbat instead of the color emoji
line 7 col 62: stray_vs15 U+FE0E (VARIATION SELECTOR-15)
  text-presentation selector after emoji U+2764; forces monochrome rendering
line 14 col 38: vs16_after_non_base U+FE0F (VARIATION SELECTOR-16)
  VS16 after non-emoji-base U+0041; wasted bytes

FAIL: 6 variation-selector finding(s)
```

`example/good.md` is the same content with VS16 properly appended
and the stray VS15 + the non-base VS16 removed:

```
$ python3 detector.py example/good.md
OK: no variation-selector issues found
```

Six findings on `bad.md`, zero on `good.md`.

## Tuning

- **Add to `BASE_NEEDS_VS16`** when you observe a new dual-use
  codepoint slipping through. The map is intentionally conservative;
  the cost of expansion is one entry per offender.
- **Allowlist a base** by removing it from the dict, or wrap `scan()`
  and post-filter on `Hit.codepoint`.
- **Skin-tone modifiers (U+1F3FB..U+1F3FF) and ZWJ (U+200D)** after
  a base are treated as "implicitly emoji-qualified" and suppress the
  `missing_vs16` finding — those sequences carry their own emoji
  presentation contract.

## Composition

- Pair with **`llm-output-zero-width-character-detector`** for full
  invisible-byte coverage. The two detectors have orthogonal scopes
  (variation selectors vs zero-width joiners / spaces / bidi) and can
  share a single CI step.
- Pair with **`llm-output-mixed-script-confusable-character-detector`**
  for the full "looks-fine-but-isn't" hygiene gate.
- Feed `(kind, codepoint, line_no)` into a one-turn repair prompt:
  *"append U+FE0F to the U+2708 at line 6 column 24"*. Deterministic,
  cheap, and the re-run of the detector is the verifier.
