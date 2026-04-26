# llm-output-numbered-list-restart-detector

Detects ordered (numbered) markdown lists that unexpectedly **restart at 1**
when they conceptually continue a prior list that was broken by an
intervening non-list paragraph.

LLMs frequently produce output like:

```
1. Pull the latest changes.
2. Run the build.
3. Verify the smoke tests pass.

Then make sure to update the changelog.

1. Tag the release.
2. Push the tag.
3. Announce in the channel.
```

A reader sees one 6-step procedure; a CommonMark renderer sees two
3-item lists with the second labeled `1, 2, 3` again. This silently
corrupts numbered references like "see step 5".

## How it works

For each ordered-list block (lines matching `^\s{0,3}\d+[.)]\s+`):

1. Track the first marker, last marker, and indent.
2. When the block closes (blank line, fence, or non-list text), remember it.
3. If the **next** ordered-list block starts with `1.`, has the same
   indent, has not been separated by a heading or thematic break, and the
   prior block ended at marker `> 1`, emit a finding.

Pure Python stdlib. Deterministic. Single pass.

## Run

```bash
python3 detector.py path/to/file.md [more.md ...]
```

Exit code:
- `0` — no findings
- `1` — at least one suspicious restart
- `2` — usage error

## Example output

Running against the bundled `examples/bad.md`:

```
$ python3 detector.py examples/bad.md
examples/bad.md:9: ordered list restarts at 1 (previous list ended at 3 on line 3)

1 finding(s).
$ echo $?
1
```

`examples/good.md` (the same content with the lists merged, plus a
legitimate restart under a new `## Rollback` heading) exits `0`.

## Tuning

- `LOOKBACK_BLANK = 2` — increase to allow more blank lines between the
  two halves of a "broken" list before treating them as unrelated.
- Headings (`#`-prefixed) and thematic breaks (`---`, `***`) reset
  state, so a deliberate `1.` start under a new heading is **not**
  flagged.

## Limitations

- Only inspects top-level (indent 0–3) lists; nested numbered sub-lists
  are not cross-checked against parent siblings.
- Cannot tell intent: a real restart that happens to follow narrative
  text without a heading will be flagged. Add a heading or horizontal
  rule to silence.
