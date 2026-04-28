# llm-output-bash-set-e-missing-detector

A pure-stdlib, code-fence-aware detector for bash/sh code blocks
emitted by an LLM that look like standalone scripts but are missing a
fail-fast preamble (`set -e`, `set -eu`, `set -euo pipefail`, or
`set -o errexit`).

## Why it matters

Bash defaults to "best effort." A failing command in the middle of a
script does *not* abort execution and does *not* change the script's
exit code, unless the very last command also fails. So when an LLM
emits a snippet like

```bash
#!/usr/bin/env bash
apt-get update
apt-get install -y libfoo-dev
./configure --prefix=/opt/app
make
make install
```

and `apt-get install` fails because the package name is wrong, every
subsequent step still runs (`./configure` against a half-installed
toolchain, `make` against missing headers, `make install` deploying a
broken binary). The user copy-pastes it, sees a wall of output, the
script exits 0, and the breakage ships.

The universally-recommended fix is a one-line preamble — `set -e` (or
the stricter `set -euo pipefail`) right after the shebang. This
detector flags blocks that need it and don't have it.

## How to run

```sh
python3 detect.py path/to/some_markdown.md
```

The script reads the file, finds every fenced code block whose
info-string first token (case-insensitive) is `bash`, `sh`, `shell`, or
`zsh`, then checks two things:

1. Is there any `set -e`-family directive in the block? If yes, skip.
2. Is the block "scripty enough" to deserve one? Either it starts
   with a `#!` shebang, OR it contains a `for` / `while` / `case`,
   a function definition, or a multi-line pipeline.

Findings go to stdout, summary to stderr, exit code is 1 when any
finding is reported and 0 otherwise. Each finding line is one of:

```
block=<N> start_line=<L> reason=no_set_e_with_shebang shebang=<...>
block=<N> start_line=<L> reason=no_set_e_with_control_flow
```

## Expected behavior on the worked examples

```
$ python3 detect.py examples/bad.md
block=1 start_line=8  reason=no_set_e_with_shebang      shebang='#!/usr/bin/env bash'
block=2 start_line=21 reason=no_set_e_with_control_flow
block=3 start_line=35 reason=no_set_e_with_control_flow
block=4 start_line=46 reason=no_set_e_with_shebang      shebang='#!/usr/bin/env bash'
total_findings=4 blocks_checked=4
$ echo $?
1

$ python3 detect.py examples/good.md
total_findings=0 blocks_checked=5
$ echo $?
0
```

So `bad.md` produces **4 findings** across 4 fenced bash/sh blocks
(install snippet, deploy function, loop+pipeline, and a `pipefail`-only
"almost-but-not-quite" preamble — pipefail without errexit still
continues past failures), and `good.md` produces **0 findings** across
5 blocks: 3 of those add the canonical preamble, and 2 are tiny
one-liner / no-control-flow snippets that fall below the detector's
"scripty enough" threshold by design.

## What is in scope

* Recognizes `set -e`, `set -eu`, `set -euo`, `set -eE`, `set -eo`,
  and `set -o errexit` as acceptable preambles.
* Ignores blocks that look like one-liners (single command, single
  line) — flagging those would be pure noise.
* Treats `set -o pipefail` *alone*, without an errexit-family
  directive, as insufficient (pipefail propagates a pipeline's exit
  code but does not make the script abort).

## What is out of scope (deliberately)

* Scripts that handle errors via explicit `|| exit` / `trap ERR`
  instead of `set -e`. We do not try to detect those — false
  negatives are preferable to false positives here.
* Detection of *partially-correct* preambles (e.g. `set -e` without
  `-u` or `pipefail`). The opinion encoded here is "any `set -e`
  family is good enough"; teams that want stricter checks can layer
  a second detector on top.
* Subshells that override the parent's `set -e` (`( cmd )` semantics).

This is a first-line sniff test, not a shellcheck replacement.
