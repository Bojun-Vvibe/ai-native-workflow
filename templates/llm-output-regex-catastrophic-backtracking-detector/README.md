# llm-output-regex-catastrophic-backtracking-detector

## Problem

LLMs frequently emit regular expressions with nested quantifiers that cause
catastrophic backtracking (a.k.a. ReDoS — Regex Denial of Service). Example
shapes seen in generated code:

* `(a+)+`, `(\w*)+`, `(.*)*` — nested unbounded quantifiers
* `(a|aa)+`, `(\w|\w+)+` — alternation with overlap under a quantifier
* `(\w+)+$` — trailing anchored greedy class (the classic email-validator trap)

These patterns can move from microsecond matches to multi-second hangs on
inputs only a few dozen characters long. They are syntactically valid, so
linters don't catch them; they only show up as latency spikes in production.

This detector scans Python, JavaScript/TypeScript, Go, Java, and Ruby source
files for regex callsites — `re.compile`, `re.search`, `new RegExp`,
`regexp.MustCompile`, etc. — extracts the literal pattern string, and runs a
set of structural checks against each one. It also accepts plain `.txt`
files containing one pattern per line.

It does **not** execute the patterns against any input. Pure stdlib `re`,
no external regex engine. Always exits `0`.

## Usage

```
python3 detector.py path/to/file.py
python3 detector.py path/to/file.js
python3 detector.py patterns.txt
cat snippet.go | python3 detector.py -
```

## Finding format

```
<path>:<line>: <code>: <message> | api=<callsite> pattern=<repr>
```

Codes:

* `REDOS000` — pattern does not compile (informational; pair with whatever
  failure mode it would produce)
* `REDOS001` — nested unbounded quantifier on `.` (e.g. `(.*)*`)
* `REDOS002` — nested quantifier in group (e.g. `(a+)+`, `(\w*)+`)
* `REDOS003` — alternation with overlap under a quantifier (e.g. `(a|aa)+`)
* `REDOS004` — trailing anchored greedy character class (e.g. `(\w+)+$`)

Trailing `# findings: <N>` summary.

## Example

```
$ python3 detector.py examples/bad.py
examples/bad.py:3: REDOS001: nested unbounded quantifier on '.' (e.g. (.*)*) ...
examples/bad.py:4: REDOS002: nested quantifier in group ...
examples/bad.py:5: REDOS004: trailing anchored greedy class ...
# findings: 3

$ python3 detector.py examples/good.py
# findings: 0
```

## Limitations

* Pattern extraction is regex-based, not a full parser; multi-line raw
  strings or string concatenation across lines may be missed.
* The structural checks intentionally err toward false negatives over false
  positives. They will not catch every ReDoS shape — pair this detector
  with a runtime budget on any regex that processes untrusted input.
* The detector flags patterns; it does not rewrite them. The fix is usually
  to anchor, atomize, or replace with a non-backtracking matcher.
