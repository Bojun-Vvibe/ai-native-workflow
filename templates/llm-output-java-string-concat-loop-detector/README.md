# llm-output-java-string-concat-loop-detector

A small Python 3 stdlib sniffer for Java source where a `String` is built
up via `+=` (or `s = s + ...`) inside a loop. This is the canonical
"use a `StringBuilder`" anti-pattern: each `+=` on a `String` allocates
a new `char[]` and copies the previous contents, turning a linear
concatenation into O(n^2).

## Why it matters for LLM-generated output

When asked for "join these into a CSV row" or "build a report string",
LLMs frequently emit:

```java
String row = "";
for (int i = 0; i < cells.length; i++) {
    row += cells[i];
    if (i < cells.length - 1) row += ",";
}
```

This compiles, runs, and passes unit tests on tiny inputs, so it slips
through review. On 10k-row inputs it pegs CPU and bloats GC pressure.
The `javac` "fold concatenation into a single `StringBuilder`" optimization
only applies to a single expression — it does **not** rescue `+=` across
loop iterations.

## Rule

Track loop scope by brace depth. A line that starts with `for (`,
`while (`, or `do {` opens a loop scope; the matching `}` closes it.
Inside any open loop scope, flag a line if:

1. It matches `<id> += <rhs>;`, AND either
   - `<id>` was previously declared as `String <id>` in the same file, OR
   - `<rhs>` starts with a string literal (`"..."`).
2. OR it matches `<id> = <id> + <rhs>;` (self-concatenation form) under
   the same conditions.

`StringBuilder.append(...)` and `StringBuffer.append(...)` calls inside
loops are intentionally **not** flagged — those are the fix.

## Limitations

- Heuristic, not a Java parser. Doesn't understand generics, lambdas,
  or string concatenation hidden behind a method return.
- Doesn't track aliasing: if `String s = otherString; for (...) s += x;`
  is across files, only the in-file declaration scan triggers the
  string-var check (the literal-RHS rule still catches the obvious case).
- Doesn't try to rewrite. For an actual fixer use an IDE or
  Error Prone's `StringSplitter`/`StringConcatToTextBlock` family.

## Usage

```
python3 detector.py <file.java> [<file.java> ...]
```

Prints `path:line: string concat in loop (var): <text>` for each
violation, then a trailing `findings: N` line. Exit code equals the
finding count (capped at 255).

## Worked example

```
$ python3 detector.py examples/Bad.java
examples/Bad.java:7: string concat in loop (row): row += cells[i];
examples/Bad.java:9: string concat in loop (row): row += ",";
examples/Bad.java:19: string concat in loop (out): out = out + unit;
examples/Bad.java:28: string concat in loop (s): s += k;
examples/Bad.java:36: string concat in loop (acc): acc += it + "\n";
examples/Bad.java:45: string concat in loop (out): out += cell;
examples/Bad.java:47: string concat in loop (out): out += "\n";
findings: 7

$ python3 detector.py examples/Good.java
findings: 0
```

`examples/Good.java` is the same set of methods rewritten with
`StringBuilder.append(...)`, plus a couple of "concatenation outside any
loop" cases that the detector correctly leaves alone.
