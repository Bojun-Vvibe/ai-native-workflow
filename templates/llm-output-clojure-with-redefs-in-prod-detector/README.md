# llm-output-clojure-with-redefs-in-prod-detector

Detects `with-redefs` (and `with-redefs-fn`) usage outside of test
namespaces / test files in Clojure / ClojureScript source.

## The antipattern

`with-redefs` thread-globally rebinds the root values of named Vars for
the dynamic extent of the body. It is the standard tool for stubbing
collaborators in unit tests. In production code it is a footgun:

- The rebinding is **process-global**, not thread-local. Other threads
  observe the redefinition mid-flight, which causes nondeterministic
  bugs that only show up under load.
- The original root value is restored in a `finally`, so an unhandled
  exception on a sibling thread that beats the restore can leave the
  Var permanently mutated.
- It hides coupling: callers of the redefined function can no longer
  reason about what implementation they are calling by reading source.
- It defeats AOT, direct linking, and the JIT's ability to inline.

The Clojure community guidance is consistent: `with-redefs` belongs
**only** in test code. Real seams (protocols, components, function
arguments, `alter-var-root` at startup) belong in production code.

## Why LLMs emit it

When asked to "patch a small piece of behavior" or "swap an
implementation at runtime", LLMs frequently reach for `with-redefs`
because it is the shortest path to the goal in REPL examples — and
REPL examples dominate their training data. They do not distinguish
between a one-off REPL snippet and a request server handler, so the
construct leaks into production paths.

## What this scanner flags

Any `(with-redefs ...)` or `(with-redefs-fn ...)` form that appears
in a file whose path does **not** look like test code. A path is
treated as test code if any of the following hold (case-insensitive):

- contains a path segment named `test`, `tests`, `spec`, `specs`, or
  `it` (integration tests)
- the filename ends in `_test.clj`, `_test.cljs`, `_test.cljc`,
  `_spec.clj`, `_spec.cljs`, `_spec.cljc`
- the file declares an `ns` whose name segment ends in `-test` or
  contains `.test.` (e.g. `(ns my.app.user-test ...)`)

Comments (`;` to end of line, plus `#_` form-level discard for the
specific `with-redefs` form) and string literals (including
`"..."` and triple-quoted-style escapes) are masked so matches
inside them do not fire.

## Usage

```bash
python3 detect.py path/to/src
```

Exit code is `1` if any findings, `0` otherwise. Output format is
`<file>:<line>:<col>: with-redefs-in-prod — <snippet>`.

To smoke-test the bundled examples:

```bash
./smoke.sh
```

It runs the scanner against `bad/` and `good/` and asserts that bad
has at least one hit and good has none.

## Suggested wiring

- Run in pre-commit on staged `.clj`/`.cljs`/`.cljc` files.
- Add to CI as a non-blocking warning at first; promote to blocking
  once the existing call sites are migrated to real seams.
- Pair with a code-review checklist item: "If this PR adds
  `with-redefs`, is the file under `test/`?"
