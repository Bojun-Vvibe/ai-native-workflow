# llm-output-php-eval-string-detector

## Purpose

Detect call sites of PHP `eval(...)` and its dynamic-code siblings
(`create_function(...)`, pre-PHP-8 `assert($string)`) outside of
comments and string literals.

`eval($code)` executes an arbitrary string as PHP source. It is one
of the classic remote-code-execution vectors: any taint reaching the
argument turns the request handler into an interpreter for the
attacker. LLM-generated PHP frequently reaches for `eval()` to
"dynamically build a function" or "run user-supplied formulas"
because it is the most direct mapping from the prompt — but the
right answer in production code is almost always a parser, a
whitelist dispatch, or `call_user_func`.

## When to use

- Reviewing LLM-generated PHP snippets before merging.
- CI lint over `*.php` / `*.phtml` / `*.inc` files in a sample dir.
- Pre-commit lint on agent-authored PHP.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `php-eval-call`
- `php-create_function-call`
- `php-assert-call` (only the bare `assert(` form; runtime determines
  whether the argument is a string or a real boolean expression)

… anywhere outside a `//` line comment, `#` line comment, `/* */`
block comment, or `'...'` / `"..."` string literal.

## What it intentionally skips

- `$obj->eval(...)` and `Class::eval(...)` — user-defined methods
  that happen to share the name are not the language builtin.
- `function eval(...)` — a user-defined function declaration (rare;
  PHP reserves the name but namespaced code can reuse it).
- Mentions inside comments or strings.

## Known false-positive sources

- The detector treats `assert(` as suspicious because the
  string-evaluating form is indistinguishable at the syntactic
  level. Modern PHP 8 code that always passes a real expression to
  `assert()` will produce a finding here; reviewers should accept
  that cost or migrate to a stricter assertion library.
- PHP `heredoc` / `nowdoc` bodies are not modeled; `eval(` literally
  appearing inside a heredoc body would be flagged.

## Files

- `detect.py` — the detector (python3 stdlib only, single-pass scan).
- `bad/` — five PHP files that MUST trigger.
- `good/` — three PHP files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_user_formula.php:4:1: php-eval-call \u2014 eval('$result = ' . $expr . ';');
bad/02_dynamic_handler.php:5:12: php-eval-call \u2014 return eval($code);
bad/03_create_function_legacy.php:3:8: php-create_function-call \u2014 $cmp = create_function('$a, $b', 'return strlen($a) - strlen($b);');
bad/04_assert_string.php:4:5: php-assert-call \u2014 assert('$value > 0 && $value < 100');
bad/05_template_render.php:5:9: php-eval-call \u2014 eval('?>' . $template . '<?php ');
# 5 finding(s)
```
