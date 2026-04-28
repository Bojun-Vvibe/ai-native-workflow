# llm-output-perl-eval-string-detector

## Purpose

Detect Perl `eval EXPR` calls (the string form of `eval`).

Perl's `eval` has two completely different forms:

1. `eval { BLOCK }` — compile-time, used for try/catch. Safe.
2. `eval EXPR`     — runtime: take a string, compile it as Perl, run it.
   This is `exec()` on a string. If any part of `EXPR` is influenced by
   user input, it is a textbook code-injection vulnerability.

LLM-emitted Perl reaches for the string form constantly — typically
`eval "use $module"` or `eval "$code_from_db"` — because it "looks
like" the JS / Python `eval`, and because models do not internalize
the block-vs-string distinction.

## When to use

- Reviewing LLM-generated Perl snippets before merging.
- CI lint over `*.pl`, `*.pm`, `*.t` files in a sample/example dir.
- Pre-commit lint on agent-authored Perl.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> \u2014 <snippet>`.

## What it flags

- `eval-string` — any bareword `eval` not immediately followed by `{`.
  Includes `eval "..."`, `eval '...'`, `eval $code`, `eval qq(...)`,
  `eval(EXPR)`.

## What it intentionally skips

- `eval { ... }` — the safe block form.
- `eval` inside a `# ...` line comment.
- `eval` inside a single- or double-quoted string literal.
- `eval` inside POD blocks (`=pod ... =cut`).
- `eval` inside heredoc bodies (best-effort, single-line tracking).

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — five Perl files that MUST trigger.
- `good/` — three Perl files that MUST NOT trigger.
- `smoke.sh` — runs the detector and asserts bad-hits > 0, good-hits == 0.

## Example output

```
$ python3 detect.py bad/
bad/01_eval_string.pl:3:1: eval-string \u2014 eval "use $mod;";
bad/02_eval_user_input.pl:5:5: eval-string \u2014 eval $user_code;
...
# 6 finding(s)
```
