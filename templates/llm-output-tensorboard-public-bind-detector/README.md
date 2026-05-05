# llm-output-tensorboard-public-bind-detector

Detect shell scripts, Dockerfiles, and Compose snippets that LLMs
commonly emit which start TensorBoard with the dashboard bound to
every interface — typically through the `--bind_all` flag (TensorBoard
2.x's "expose to the network" shortcut) or by passing
`--host=0.0.0.0` (or `--host 0.0.0.0`) on the command line.

TensorBoard ships with **no authentication** of any kind. Its threat
model assumes the dashboard is reached over `localhost` only. Once
bound to a public interface, every visitor can:

- Browse every scalar / histogram / image summary the run logged,
  which routinely contains training data samples, prompts, and model
  outputs.
- Read arbitrary files inside the configured `--logdir` via the
  built-in plugin file handlers (the `What-If`, `Profile`, and
  `Debugger V2` plugins all expose file-fetching endpoints).
- Inspect the served model's compute graph via the `Graphs` plugin,
  which leaks layer names, shapes, and any embedded constants.

The TensorBoard release notes for `--bind_all` (added in 2.0) and the
upstream FAQ both explicitly call this out: "TensorBoard does not
have authentication; do not use `--bind_all` on a public network".
LLMs ignore this warning every time they're asked "make TensorBoard
reachable from my laptop" or "run TensorBoard in Docker".

The hardening guidance is to leave the default `--host=localhost` in
place and front the dashboard with an authenticated reverse proxy
(nginx + basic auth, an SSO gateway, or an SSH tunnel). The fix is
removing the offending flag, not adding one.

This detector is orthogonal to every other "public bind" detector in
the repo: those target server config files (Mongo `bindIp`, Redis
`bind`, Kibana `server.host`, etc.); this one targets a CLI invocation
of a Python tool and the shapes that show up inside Dockerfiles,
Compose files, and shell wrappers.

Related weaknesses: CWE-306 (Missing Authentication for Critical
Function), CWE-284 (Improper Access Control), CWE-200 (Exposure of
Sensitive Information to an Unauthorized Actor).

## What bad LLM output looks like

Direct invocation with `--bind_all`:

```sh
tensorboard --logdir runs/ --bind_all
```

Dockerfile `CMD` form (the canonical "deploy TensorBoard" snippet):

```dockerfile
CMD ["tensorboard", "--logdir=/logs", "--bind_all", "--port=6006"]
```

Long-form `--host=0.0.0.0`:

```sh
tensorboard --logdir=./runs --host=0.0.0.0 --port=6006
```

Space-separated `--host 0.0.0.0`:

```sh
tensorboard --logdir ./runs --host 0.0.0.0
```

## What good LLM output looks like

- The default — no `--host` flag and no `--bind_all` — which keeps
  TensorBoard bound to `localhost`.
- Explicit `--host=localhost` or `--host=127.0.0.1`.
- A loopback-only invocation forwarded over SSH (`ssh -L 6006:...`).
- The flag appears only inside a `# comment` or a heredoc that is
  never executed (the detector strips shell comments).

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/dockerfile_bind_all.Dockerfile
BAD  samples/bad/run_tensorboard_bind_all.sh
BAD  samples/bad/run_tensorboard_host_space_zero.sh
BAD  samples/bad/run_tensorboard_host_zero.sh
GOOD samples/good/run_tensorboard_default.sh
GOOD samples/good/run_tensorboard_host_localhost.sh
GOOD samples/good/run_tensorboard_host_loopback_ip.sh
GOOD samples/good/run_tensorboard_with_comment_only.sh
bad=4/4 good=0/4 PASS
```

Exit status is `0` only when every bad sample is flagged and zero
good samples are flagged.

## Detector rules

A file is flagged iff, after `#`-comment stripping, at least one of
the following is true on a line that also contains the bare token
`tensorboard` (a word boundary on each side, so `tensorboardX` does
not match):

1. **`--bind_all`** appears as a standalone token (whitespace, `=`,
   end of line, or quote on each side).
2. **`--host=0.0.0.0`** appears (with or without quotes around the
   value).
3. **`--host 0.0.0.0`** appears (space-separated form, with or
   without quotes around the value).

`#` line comments and inline `# ...` tails are stripped before
matching. JSON-array `CMD` / `ENTRYPOINT` forms in Dockerfiles match
because the `--bind_all` / `--host=0.0.0.0` token appears inside the
quoted argument list on the same line as the `tensorboard` token.

## Known false-positive notes

- A line like `# tensorboard --bind_all` (commented out) is treated
  as good; the comment stripper removes the entire line first.
- A line that mentions `tensorboard` purely in prose (e.g.,
  `echo "Use tensorboard with --bind_all only on localhost"`) will
  match, since the detector cannot distinguish prose from
  invocation. Prefer not to embed example invocations inside echo
  strings; quote them in Markdown instead.
- The `tensorboard.main` Python module entrypoint
  (`python -m tensorboard.main --bind_all`) is matched: the bare
  token `tensorboard` appears on the line.
- A custom wrapper named `my-tensorboard-launcher` is *not* flagged
  unless it spawns `tensorboard` on the same line; the detector
  inspects only the visible invocation.
