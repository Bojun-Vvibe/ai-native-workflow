# llm-output-markdown-fenced-code-fence-length-consistency-detector

## What this catches

CommonMark allows fenced code blocks to use any run of 3+ backticks (or
tildes) as a fence, and the closing fence only needs to match the same
character with **at least** the same length. LLMs occasionally vary the
fence length within a single document — opening some blocks with
` ``` `, others with ` ```` `, and mixing tildes too. While usually
parseable, the inconsistency:

- breaks naive regex-based extractors (downstream tooling that assumes a
  single canonical fence length),
- causes diff churn when one model run uses 3 and the next run uses 4,
- and hides a class of bug where a 4-tick opener never closes because
  the model emits a 3-tick closer.

This detector reports every fenced code block whose opening fence length
or marker character differs from the document's most common opener.

## Why it matters for AI-native workflows

When evaluation harnesses extract code blocks from model output (for
auto-execution, syntax checking, or test runners), inconsistent fence
shapes are a leading cause of "ghost" code — a block the human reader
sees in a rendered preview but the extractor silently drops because its
regex was tuned to the dominant shape.

## Files

- `detector.py` — the detector. Exit `0` clean, `1` if findings.
- `bad.md` — mixes 3-backtick, 4-backtick, and 3-tilde openers.
- `good.md` — uses one consistent fence shape throughout.

## Usage

```
python3 detector.py path/to/file.md
```

## Verified runnable

```
$ python3 detector.py good.md ; echo "exit=$?"
exit=0
$ python3 detector.py bad.md ; echo "exit=$?"
bad.md:11: fence opener '````' differs from dominant '```'
bad.md:17: fence opener '~~~' differs from dominant '```'
exit=1
```

## Rule shape

1. Walk the document, tracking fence open/close state.
2. A fence opener is the first non-fenced line matching
   `^ {0,3}(`{3,}|~{3,})`.
3. A fence closer is a line that matches the same marker character with
   length >= the opener's length and nothing else on it.
4. Tally `(marker_char, length)` across all openers; the most frequent
   pair is the dominant shape. Report every opener that doesn't match.
