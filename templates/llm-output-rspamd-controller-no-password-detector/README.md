# llm-output-rspamd-controller-no-password-detector

Static detector for rspamd configurations whose **controller worker**
ships without a password. The controller worker exposes both the
WebUI and the management HTTP API; if its `password` /
`enable_password` keys are absent, blank, or set to a known weak
upstream literal (`q1`, `password`, `rspamd`, `admin`, `changeme`),
anyone reaching the listener can drive scan config, learn bayes,
flush stats, and read mail metadata.

## Why

The upstream rspamd documentation example uses `password = "q1";`
purely to illustrate hashing. Operators frequently copy the snippet
verbatim, leave the literal in place, or comment the line out
entirely. The result is a controller listening on a routable
interface with no auth.

This detector flags four shapes:

1. UCL `worker "controller" { ... }` block with neither `password`
   nor `enable_password` set.
2. Same block where the value is an empty string or a documented
   weak literal.
3. `local.d/worker-controller.inc` overrides that explicitly blank
   the password.
4. Container surfaces — `RSPAMD_PASSWORD=` blank in compose env or
   `rspamd ... -p ""` in a Dockerfile / compose `command:` line.

## When to use

- Reviewing LLM-emitted rspamd config snippets before applying them.
- Pre-merge gate on `infra/mail/**` config repos.
- Spot check on container image build scripts.

## Suppression

Same line or the line directly above:

```
# rspamd-controller-no-password-allowed
```

Use sparingly — typically only for ephemeral local-dev compose
overrides on a loopback bind.

## How to run

```sh
./verify.sh
```

This runs `detector.py` against every fixture under `examples/bad`
and `examples/good` and prints a `bad=N/N good=0/N PASS` summary.

## Direct invocation

```sh
python3 detector.py path/to/worker-controller.inc
```

Exit code is the number of files with at least one finding (capped
at 255). Stdout lines are formatted `<file>:<line>:<reason>`.

## Limitations

- The UCL scan is line-oriented. Pathologically nested includes that
  define the password in a separate file are not stitched together;
  point the detector at every include in the same invocation if you
  want full coverage.
- The detector does not validate password strength beyond the small
  weak-literal denylist.
