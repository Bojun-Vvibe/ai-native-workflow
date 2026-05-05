# llm-output-redis-no-requirepass-detector

Detects LLM-emitted Redis configs and launch commands that leave the
server reachable with no `requirepass` set — the classic open-Redis
footgun that ends in `FLUSHALL`, crypto-miner installs via `CONFIG SET
dir`, or worse.

Distinct from `llm-output-redis-protected-mode-no-detector`: that one
fires only on `protected-mode no`. This one fires on the broader class
of "no real auth password" — including public binds without a password,
`redis-server` shell launches missing `--requirepass`, and well-known
placeholder passwords (`changeme`, `password`, `foobared`, empty string).

CWE-306 (Missing Authentication for Critical Function) and CWE-521
(Weak Password Requirements) for the placeholder-password case.

## What this catches

| # | Pattern                                                                                  |
|---|------------------------------------------------------------------------------------------|
| 1 | `redis.conf` with no `requirepass` directive AND `bind 0.0.0.0` / `bind ::` / empty bind |
| 2 | `redis.conf` with no `requirepass` directive AND `protected-mode no`                     |
| 3 | Dockerfile / shell / compose that runs `redis-server` with no `--requirepass` flag       |
| 4 | `requirepass` set to an empty string or a known placeholder (`changeme`, `password`, …)  |

## Usage

```bash
python3 detector.py examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. Final
stdout line: `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It executes the detector
against the bundled samples and asserts `bad=4/4 good=0/4 PASS`.
