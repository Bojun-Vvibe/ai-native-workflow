# llm-output-java-spel-injection-detector

Stdlib-only Python detector that flags Java code parsing a Spring
Expression Language (SpEL) string built from a non-literal value.

SpEL is a fully featured expression language: a parsed-and-evaluated
expression can invoke arbitrary Java methods
(`T(java.lang.Runtime).getRuntime().exec(...)`), so any
`parser.parseExpression(<dynamic>)` followed by `.getValue(...)` is a
**CWE-94** (code injection) sink. Real-world incidents include
CVE-2022-22963 (Spring Cloud Function) and CVE-2018-1273.

LLMs love this anti-pattern when asked "evaluate a user-supplied
formula in Spring": the model reaches for `SpelExpressionParser`,
concatenates the request parameter into the expression text, and
evaluates it against a fresh `StandardEvaluationContext` (which is
permissive by default and exposes type references via `T(...)`).

## Why "parseExpression + non-literal" is the right anchor

`SpelExpressionParser` is the canonical entrypoint. The arguments that
turn it dangerous are *inputs to that one method call*, so anchoring on
`parseExpression(...)` and inspecting its argument shape is both
precise and resilient to import-style and helper-wrapper variation.

## Heuristic

A finding is emitted when **the file references SpEL** (either
`SpelExpressionParser` or `org.springframework.expression`) AND the
`parseExpression(...)` argument is not a single string literal AND any
of these signals fires:

1. The argument contains string concatenation (`"..." + name`).
2. The argument expression itself names a tainted source
   (`getParameter`, `getHeader`, `RequestParam`, `PathVariable`,
   `RequestBody`, `RequestHeader`, `ServletRequest`).
3. The argument is a bare identifier and a tainted source is visible
   earlier in the same file (the model has hoisted the request value
   into a local variable before passing it in).

The detector does **not** flag:

- `parser.parseExpression("'hello'")` — pure string literal.
- `parser.parseExpression("1 + 2 * 3")` — no concatenation, no
  identifier, no upstream taint.
- A literal expression evaluated against `StandardEvaluationContext`
  (permissive context alone is not enough).
- Files without any SpEL anchor (the bare token `parseExpression`
  could be a different parser library).

## CWE / standards

- **CWE-94**: Improper Control of Generation of Code ("Code
  Injection").
- **CWE-95**: Eval Injection (parent of dynamic-language eval).
- **OWASP A03:2021** — Injection.

## Limits / known false negatives

- Does not follow taint across files or via getter chains
  (`dto.getFormula()`).
- Does not flag a literal expression that hard-codes a `T(...)` type
  reference without dynamic input — that is intentional API use.
- Does not parse Java; relies on regex over the flat source text.

## Usage

```bash
python3 detect.py path/to/File.java
python3 detect.py path/to/dir/   # walks *.java and *.java.txt
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=5/5 good=0/5
PASS
```

Layout:

```
examples/bad/
  01_concat_request_param.java   # "1 + " + userInput
  02_request_param_direct.java   # @RequestParam String formula
  03_servlet_getparameter.java   # request.getParameter("q") -> SpEL
  04_pathvariable_concat.java    # "user." + @PathVariable
  05_header_value.java           # request.getHeader("X-Filter")
examples/good/
  01_pure_literal.java           # "'hello, world'"
  02_constant_template.java      # "1 + 2 * 3"
  03_unrelated_parser.java       # parseExpression on non-SpEL parser
  04_literal_method_chain.java   # literal expression + StandardEvalCtx
  05_no_spel_anchor.java         # no SpEL import in file
```
