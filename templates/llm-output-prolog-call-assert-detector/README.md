# llm-output-prolog-call-assert-detector

Pure-stdlib python3 single-pass scanner that flags Prolog's
dynamic-goal sinks: `call/N`, `assert`/`assertz`/`asserta`,
`retract`/`retractall`, `term_to_atom`, and `read_term_from_atom`.

## What it detects

In Prolog, a goal is just a term. Any term reachable through
`call/N` is interpreted as a goal at run time. If the term came from
a user-controlled atom, a clause asserted at run time, or a string
round-tripped through `term_to_atom/2`, you have the same blast
radius as `eval($USER_INPUT)` in any other language — and because
Prolog's resolution machinery is Turing-complete, the attacker does
not even need the host shell to get arbitrary control.

| Sink                       | Hazard                                                     |
| -------------------------- | ---------------------------------------------------------- |
| `call/1 .. call/8`         | Interpret the term as a goal at run time.                  |
| `apply/2`                  | Deprecated SWI form, same hazard as `call`.                |
| `assert/1`, `asserta/1`, `assertz/1` | Install a clause into the database at run time.  |
| `retract/1`, `retractall/1`| Wipe rules out from under the program.                     |
| `term_to_atom/2`           | Atom↔term parser; routinely paired with `call`.            |
| `read_term_from_atom/3`    | Explicit atom-to-term re-parse, then `call`.               |

LLM-emitted Prolog reaches for `call` to "execute a predicate whose
name lives in a variable". That is almost always wrong. Safe forms:

* keep a closed allowlist of goal terms and dispatch on it explicitly;
* use higher-order combinators (`maplist/2`, `foldl/4`) where the
  predicate symbol is a literal in source;
* never feed an atom built from user input into `call` or `assert`.

## What gets scanned

* Files with extension `.pro`, `.prolog`, `.P` (always treated as
  Prolog).
* Files with extension `.pl` only when one of the following holds:
  * a Prolog-ish shebang on line 1 (`swipl`, `gprolog`, `yap`,
    `sicstus`), or
  * a directive line (`:- ...`) appears within the first 40 lines.
  This is the standard way to disambiguate Prolog `.pl` from Perl
  `.pl` without false positives.
* Files with a Prolog-ish shebang regardless of extension.
* Directories are recursed.

## Suppression marker

A trailing `% call-ok` (or `%% call-ok`) on the same line suppresses
that line.

```prolog
call(Goal).  % call-ok  Goal is a literal in source, not user input
```

## False-positive notes

* The trigger words inside a `% ...` line comment, a `/* ... */`
  block comment (handled across line boundaries), a `"..."` string,
  or a `'...'` quoted atom are all scrubbed before scanning.
* Predicates whose names merely *contain* the trigger token —
  `mycall`, `asserter`, `recall` — are NOT flagged. The regex requires
  a non-word character on the left.
* The regex requires the trigger to be immediately followed by `(`,
  matching Prolog's functor-application syntax. A bareword `call`
  used as data (e.g. `[call, assertz]`) is not a sink and not flagged.
* SWI-specific `shell/1`, `process_create/3`, `meta_predicate`
  declarations, and `=..` (univ) are out of scope.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: prolog-<sink> — <stripped source line>
# <N> finding(s)
```

## Live smoke test

```
$ python3 detect.py examples/bad/
examples/bad/bad1.pro:5:5: prolog-term-to-atom — term_to_atom(Goal, UserAtom),
examples/bad/bad1.pro:6:5: prolog-call — call(Goal).
examples/bad/bad2.pro:5:5: prolog-assertz — assertz((Head :- Body)).
examples/bad/bad3.prolog:5:5: prolog-call — call(F, X, Y).
examples/bad/bad4.pro:5:5: prolog-read-term-from-atom — read_term_from_atom(A, Goal, []),
examples/bad/bad4.pro:6:5: prolog-call — call(Goal).
examples/bad/bad5.pro:5:5: prolog-retractall — retractall(Functor).
examples/bad/bad6.pl:5:9: prolog-call — a(G) :- call(G).
examples/bad/bad6.pl:6:12: prolog-asserta — b(H, B) :- asserta((H :- B)).
# 9 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

`bad/` has 6 files producing 9 findings (bad1, bad4, bad6 each
contain two sinks). `good/` has 4 files producing 0 findings: a
closed-allowlist dispatcher, a file where the trigger words appear
only inside comments and strings, an audited use suppressed with
`% call-ok`, and three benign predicates whose names merely contain
the trigger substring.

## Implementation notes

* Single-pass per line after a file-level `/* ... */` block-comment
  scrub (block comments may span lines).
* Each line additionally has `% ...` line comments, `"..."` strings,
  and `'...'` quoted atoms blanked out (column-preserving) before
  the regex runs.
* The `0'C` character-code literal is left intact — it cannot
  contain a sink word.
* No third-party deps. python3 stdlib only (`re`, `sys`, `pathlib`).
