# llm-output-javascript-loose-equality-detector

A pure-stdlib, code-fence-aware detector for JavaScript / TypeScript
code blocks emitted by an LLM that use the loose-equality operators
``==`` and ``!=`` instead of strict ``===`` / ``!==``.

## Why it matters

JavaScript's loose equality applies the abstract-equality algorithm,
which performs implicit type coercion. The classic surprises:

```
0       ==  ""         // true
0       ==  "0"        // true
false   ==  "0"        // true
null    ==  undefined  // true
" \t\n" ==  0          // true
[1]     ==  "1"        // true
[1,2]   ==  "1,2"      // true
```

Strict equality (``===`` / ``!==``) does *not* coerce; it returns
``true`` only when both operands have the same type **and** value.
Eslint's ``eqeqeq`` rule, the Airbnb style guide, the Google style
guide, and the TypeScript recommended config all default to "always
use ``===``" for exactly this reason.

LLMs frequently emit ``if (x == null)`` (the only widely-defended use
of ``==``, intended to catch both ``null`` and ``undefined``) but
they also emit ``if (count == 0)``, ``while (s != "")``, and
``return code == 200`` — which are bugs waiting to happen. This
detector flags every loose-equality occurrence, but exposes a
per-finding ``reason`` so a reviewer can quickly skim past the
deliberate ``== null`` idiom if their team allows it.

## How to run

```sh
python3 detect.py path/to/some_markdown.md
```

The script reads the file, finds every fenced code block whose
info-string first token (case-insensitive) is one of ``javascript``,
``js``, ``jsx``, ``typescript``, ``ts``, ``tsx``, ``mjs``, ``cjs``,
or ``node``, and runs a small hand-rolled scanner that understands:

* ``//`` line comments
* ``/* ... */`` block comments
* Single-quoted, double-quoted, and template-literal strings
  (with ``${...}`` interpolations)
* Regex literals (``/.../flags``) using a context-based heuristic so
  that division operators are not mistaken for regexes

Inside *code*, the scanner recognizes the operators ``==``, ``!=``,
``===``, ``!==`` and reports the first two. The ``===`` and ``!==``
operators are accepted. When the right-hand operand is the bare
identifier ``null``, the finding is tagged ``reason=loose_eq_null``;
otherwise ``reason=loose_eq``.

Findings go to stdout, summary to stderr, exit code is ``1`` when
any finding is reported and ``0`` otherwise. Each finding line
looks like:

```
block=<N> start_line=<L> in_block_line=<l> col=<c> op=<op> reason=<r>
```

## Expected behavior on the worked examples

```
$ python3 detect.py examples/bad.md
block=1 start_line=9  in_block_line=2 col=15 op===  reason=loose_eq
block=2 start_line=20 in_block_line=2 col=19 op===  reason=loose_eq
block=2 start_line=20 in_block_line=3 col=19 op=!=  reason=loose_eq
block=3 start_line=30 in_block_line=2 col=11 op===  reason=loose_eq_null
block=3 start_line=30 in_block_line=4 col=20 op===  reason=loose_eq
block=4 start_line=41 in_block_line=5 col=18 op===  reason=loose_eq
total_findings=6 blocks_checked=4
$ echo $?
1

$ python3 detect.py examples/good.md
total_findings=0 blocks_checked=5
$ echo $?
0
```

(The ``op=`` field renders the actual two-character operator after
the equals sign, so ``op===`` means the operator is ``==``, and
``op=!=`` means ``!=``.)

So ``bad.md`` produces **6 findings** across 4 fenced JS/TS blocks
(``count == 0``; ``code == 200`` and ``code != 200``; ``a == null``
deliberately tagged ``loose_eq_null`` and another ``== "yes"``;
plus a real ``n == 1`` while the ``==`` inside the template literal,
inside the regex literal, and inside the comment are correctly
ignored). ``good.md`` produces **0 findings** across 5 JS/TS blocks
(strict operators, an explicit ``=== null || === undefined`` check
that replaces the loose-eq-null idiom, equality-looking content
inside strings/regexes/comments, and a block with no equality at
all). One ``python`` block in ``good.md`` is correctly skipped via
the fence info-string.

## What is in scope

* Loose-equality operators ``==`` and ``!=`` in real code positions.
* JS, JSX, TS, TSX, mjs, cjs, and ``node``-tagged blocks.
* Operators inside ``${...}`` interpolations *of* a template literal
  are correctly recognized as code (the scanner tracks brace depth
  inside template expressions).

## What is out of scope (deliberately)

* Sophisticated control-flow analysis to determine whether a
  ``== null`` is "intended for both null and undefined." We surface
  that case as a distinct ``reason`` and let humans decide.
* JSX prop expressions are scanned just like normal code, so an
  attribute value such as ``checked={x == 1}`` will be flagged. That
  is intentional.
* Comparison-like patterns inside JSDoc ``@param`` text are scanned
  as comments and therefore ignored — the scanner skips ``/* ... */``
  contents wholesale.
* We do not try to detect ``Object.is(...)`` misuse, NaN-equality
  pitfalls, or coercion in the ``switch`` ``case`` matcher (which
  uses strict equality natively in JS).

This is a first-line sniff test, not an eslint replacement.
