# llm-output-d-mixin-detector

Single-pass detector for **D-language `mixin(...)` string-evaluation**
sites — D's compile-time `eval` equivalent. Whenever the argument to
`mixin` is anything other than a manifest, audited string literal, the
construct is either a code-injection sink (when the string is built
from imported file contents or external input via CTFE) or an obscure
metaprogramming trick that should be a proper `template` /
`static foreach` instead.

## Why this exists

D's `mixin` expression takes a `string` and compiles it as D source in
place. LLM-emitted D code reaches for `mixin` whenever the model
doesn't know the right metaprogramming primitive. Examples that look
innocuous but should always get a human review:

```d
mixin("int " ~ name ~ " = " ~ value.to!string ~ ";");
mixin(import("schema.txt"));            // CTFE file -> code
mixin(generateAccessors!T);             // template-built source
```

Each of these compiles attacker-controllable text into the binary.

## What it flags

| Construct                 | Why                                       |
| ------------------------- | ----------------------------------------- |
| `mixin("...")`            | String mixin, even with a literal arg     |
| `mixin(buildExpr())`      | Built string — true eval-style sink       |
| `mixin (\n  expr\n)`      | Whitespace / multiline tolerated          |
| `mixin(q"{...}")`         | Token-string literal still passes through |
| `mixin!"..."`             | Template-bang shorthand with code string  |

## What it ignores

- **Template mixins**: `mixin Logger!"tag";`, `mixin Foo!();` —
  the argument is a template identifier, not code text. Not flagged.
- Mentions of `mixin(` inside `// line`, `/* block */`, `/+ nested
  /+ inner +/ outer +/` comments, or inside `"..."`, `` `...` ``,
  `r"..."`, `q"(...)"`-family string literals.
- Lines marked with the suppression comment `// mixin-ok`.

## Usage

```sh
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code `1` on any finding, `0` otherwise. Python 3 stdlib only,
no third-party dependencies. Recurses into directories looking for
`*.d` and `*.di`.

## Verified output

Run against the bundled examples:

```
$ python3 detect.py examples/bad.d
examples/bad.d:17:5: d-mixin-call — mixin("int a = 1 + 2;");
examples/bad.d:20:5: d-mixin-call — mixin(buildAssign("b", 7));
examples/bad.d:23:5: d-mixin-call — mixin (
examples/bad.d:29:5: d-mixin-call — mixin(q"{int d = 42;}");
examples/bad.d:33:5: d-mixin-bang-string — mixin!"int e = 100;";
# 5 finding(s)

$ python3 detect.py examples/good.d
# 0 finding(s)
```

The `good.d` file deliberately includes:

- a template-mixin `mixin Logger!"service"` (no parens, no
  string-mixin shorthand → not flagged),
- a string literal containing the substring `mixin(...)` in prose,
- `// line`, `/* block */`, and `/+ nested /+ inner +/ outer +/`
  comments mentioning `mixin(evil)`,
- one suppressed `mixin("int z = 1;");` with the `// mixin-ok`
  marker on the same line.

All five are correctly *not* flagged.

## Design notes

- **Single pass per file**, two compiled regexes, full D source
  masking pipeline that handles `//`, `/* */`, `/+ +/` (with
  proper nesting), `"..."` with escapes, `` `...` `` WYSIWYG,
  `r"..."` raw, and `q"X...X"` token strings (with paired
  delimiters `()`, `[]`, `{}`, `<>`).
- The masker preserves column positions and newlines so the
  detector reports accurate `file:line:col` coordinates.
- Suppression marker `// mixin-ok` lets you whitelist a single line
  when the mixin is intentional and the source string has been
  audited.

## Layout

```
detect.py            # the scanner
examples/bad.d       # five intentional violations
examples/good.d      # zero violations, including a suppressed line
```
