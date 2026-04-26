# llm-output-fence-mismatched-tilde-backtick-detector

Detects fenced code blocks where the **opening** marker uses one fence
character (backtick) but a later line tries to **close** with the
other (tilde), or vice versa.

Per CommonMark, a fence opened with `` ``` `` can only be closed by a
line of `` ``` `` (or longer); `~~~` does **not** close it. LLMs
routinely confuse the two:

````
```python
print("hi")
~~~
````

A renderer keeps the backtick fence open and silently swallows
everything after the `~~~` as code text, often running to end of file.
The error is invisible in raw source.

## How it works

For every line, the scanner tracks at most one open fence at a time:

1. Match an opener `^\s{0,3}(`{3,}|~{3,})...$` and remember kind + length.
2. While a fence is open:
   - A line of `>= N` of the **same** kind closes it (resets state).
   - A line of `>= 3` of the **other** kind is reported as a
     mismatched-close finding, and treated as a forgiving close so the
     scanner doesn't cascade-flag the rest of the document.
3. At EOF, any still-open fence is reported as "never closed".

Pure Python stdlib. Single pass. Deterministic.

## Run

```bash
python3 detector.py path/to/file.md [more.md ...]
```

Exit code:
- `0` — no findings
- `1` — at least one mismatched or unclosed fence
- `2` — usage error

## Example output

```
$ python3 detector.py examples/bad.md
examples/bad.md:8: line looks like a closing fence '~~~' but the open fence on line 5 is '```' — kinds must match
examples/bad.md:14: line looks like a closing fence '```' but the open fence on line 12 is '~~~' — kinds must match

2 finding(s).
$ echo $?
1
```

`examples/good.md` (same content with each fence consistently
backtick-or-tilde) exits `0`.

## Limitations

- Only one open fence is tracked at a time (CommonMark does not nest
  fences of the same kind).
- A short closer (e.g. `` `` `` after an opener of `` ```` ``) is
  treated as content, matching CommonMark behavior — it will not
  close the block, and the unclosed-EOF check will catch it.
- Info strings on the opener are ignored for kind-matching purposes.
