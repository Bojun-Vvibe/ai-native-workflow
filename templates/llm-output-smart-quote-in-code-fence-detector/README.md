# llm-output-smart-quote-in-code-fence-detector

LLMs (and the rendering layers in front of them) sometimes auto-curl
straight quotes into "smart" / typographic quotes. That is fine in
prose, but inside a fenced code block it silently breaks the snippet:
`print("hi")` is valid Python, `print(“hi”)` is a `SyntaxError`. The
same hazard applies to JSON, shell, YAML, and basically every
machine-parsed format.

This checker isolates every fenced code block in a markdown document
and reports every curly-quote character it finds inside, with line,
column, Unicode codepoint, and the block's language tag.

## Detected characters

| Char | Codepoint | Name                          |
|------|-----------|-------------------------------|
| `'`  | U+2018    | LEFT SINGLE QUOTATION MARK    |
| `'`  | U+2019    | RIGHT SINGLE QUOTATION MARK   |
| `"`  | U+201C    | LEFT DOUBLE QUOTATION MARK    |
| `"`  | U+201D    | RIGHT DOUBLE QUOTATION MARK   |
| `'`  | U+2032    | PRIME                         |
| `"`  | U+2033    | DOUBLE PRIME                  |

## Usage

```sh
python3 check.py example.md
# or pipe markdown in
cat README.md | python3 check.py
```

Stdlib only. Exit code `0` when clean, `1` otherwise. Wire into a
pre-commit hook or a docs CI step so leaked smart quotes are caught
before users copy-paste broken snippets.

## Worked example

`example.md`:

````
Here is how to greet the world.

```python
print("hello, world")
name = 'alice'
```

And the JSON variant:

```json
{"user": "alice", "role": "admin"}
```

Inline prose with "smart quotes" is fine and should not be flagged.

```sh
echo 'plain ascii is fine'
```
````

Run:

```sh
$ python3 check.py example.md
Found 12 smart-quote leak(s) inside fenced code blocks:
  line 4 col 7: '"' U+201C LEFT DOUBLE QUOTATION MARK  [block: python]
  line 4 col 20: '"' U+201D RIGHT DOUBLE QUOTATION MARK  [block: python]
  line 5 col 8: ''' U+2018 LEFT SINGLE QUOTATION MARK  [block: python]
  line 5 col 14: ''' U+2019 RIGHT SINGLE QUOTATION MARK  [block: python]
  line 11 col 2: '"' U+201C LEFT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 7: '"' U+201D RIGHT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 10: '"' U+201C LEFT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 16: '"' U+201D RIGHT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 19: '"' U+201C LEFT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 24: '"' U+201D RIGHT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 27: '"' U+201C LEFT DOUBLE QUOTATION MARK  [block: json]
  line 11 col 33: '"' U+201D RIGHT DOUBLE QUOTATION MARK  [block: json]
```

Note that the inline prose `"smart quotes"` outside any fence is
correctly **not** flagged — the checker is intentionally scoped to
code blocks, where the cost of a curl is highest.

## Notes

- Fences are recognized using CommonMark-style rules: 3+ backticks or
  3+ tildes, with up to 3 leading spaces, closed by a fence of the
  same character and at least the same length and an empty info
  string.
- Indented (4-space) code blocks are not currently scanned. Most
  modern markdown is fence-based, and indented blocks are easy to add
  if needed.
- The block's language tag (info string) is included in each leak
  line so a fixer script can apply language-aware normalization
  (e.g. always rewrite to `'` in `python`, always to `"` in `json`).
