# llm-output-perl-do-file-detector

Static detector for Perl's **file-based code-load** sinks (`do EXPR`, `require EXPR`) in `.pl` / `.pm` / `.t` files an LLM may emit when wiring up "load this plugin path" or "reload the user's script".

## Problem

Perl's `do EXPR` is the file-loading cousin of `eval STRING`: when `EXPR` evaluates to a *filename* (a scalar, an interpolated string, a `qq{}` form, an arbitrary expression), Perl reads the file, parses it, and executes it in the current package. A user-controlled path means RCE.

`require EXPR` behaves the same way when `EXPR` is **not** a bareword. `require Foo::Bar` (bareword) is the normal module-loading idiom and is safe; `require $path` and `require "Foo/$x.pm"` are runtime file loads driven by a runtime-computed path.

| Sink | Why it's flagged |
|------|------------------|
| `do $path` | runtime file load, scalar path |
| `do "plugins/$x.pl"` | runtime file load, interpolated path |
| `do qq{addons/$tag.pl}` | quote-like form of the above |
| `do(glob(...))` / `do(...)` | parenthesized non-block expression |
| `require $mod` | runtime require, scalar path |
| `require "Foo/$x.pm"` | runtime require, interpolated path |

This detector is intentionally distinct from `llm-output-perl-eval-string-detector` (which targets `eval STRING`). The two sinks are siblings: one runs a string as code, the other runs a file as code.

## What the detector flags

- `do-scalar` — `do $var`
- `do-interp-string` — `do "..."` (any double-quoted form)
- `do-q-bracket` — `do q{...}` / `do qq{...}` / `do qw{...}` / `do qr{...}`
- `do-paren-expr` — `do(...)` (non-block parenthesized expression)
- `require-scalar` — `require $var`
- `require-interp` — `require "..."`

## What it deliberately does NOT flag

- `do { BLOCK }` — control-flow construct, not a file load.
- `require Module::Name` — bareword require (normal module loading).
- `use Module qw(...)` — compile-time module load.
- Any sink mention inside a `# ...` line comment, a `=pod ... =cut` POD block, a single-/double-/backtick-quoted string body, a `q{}` / `qq{}` / `qw{}` body, or a heredoc body — all are masked before regex matching. The detector preserves the *prefix* of quote-like forms (`q`, `qq`, `qr`, `qw`) and the opening delimiter so that `do qq{...}` is still recognized as a sink.

## How it works

Single pass, python3 stdlib only (`detector.py`). The `mask()` function tracks four mutually-exclusive states (POD block, regular string, quote-like operator body, heredoc body) plus line-start awareness for POD `=word` / `=cut` and heredoc terminator detection. Comments, POD, and string interiors are blanked while newlines are preserved so reported line numbers stay accurate. Six compiled regexes then run per masked line; first match wins per line.

## Usage

```sh
python3 detector.py path/to/lib/ bin/loader.pl
```

Exit code `1` if any finding is emitted, `0` otherwise — drop straight into pre-commit / CI.

## Live smoke test

```
$ bash verify.sh
== bad/ ==
bad/01_do_scalar.pl:7:10: do-scalar my $rv = do $path;
bad/02_do_interp_string.pl:6:10: do-interp-string my $rv = do "plugins/$name.pl";
bad/03_do_qq_bracket.pl:7:10: do-q-bracket my $rv = do qq{addons/$tag/init.pl};
bad/04_do_paren_expr.pl:5:1: do-paren-expr do(glob("/tmp/payload-*.pl"));
bad/05_require_scalar.pl:6:1: require-scalar require $mod_path;
bad/06_require_interp.pl:7:1: require-interp require "Plugins/$name.pm";
bad/07_after_pod.pl:14:1: do-scalar do $script;
bad/08_after_heredoc.pl:13:1: require-interp require "remote/$ARGV[0].pm";
== good/ ==
-- summary --
bad-findings:  8  (expected: >= 8)
good-findings: 0 (expected: 0)
PASS
```

The `good/` corpus deliberately exercises every false-positive trap: `do { BLOCK }` blocks, bareword `require`s, comment-only mentions, POD-block mentions, string-literal mentions, and a hard-coded plugin-registry alternative.
