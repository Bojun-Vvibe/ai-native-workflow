# llm-output-drone-rpc-secret-weak-detector

Detects LLM-emitted Drone CI configs that ship a weak or placeholder
`DRONE_RPC_SECRET` (or `DRONE_AGENT_SECRET` / `DRONE_RUNNER_SECRET`).

The RPC secret is the shared HMAC key between the Drone server and
every runner. A weak value lets anyone who can reach the server
register a rogue runner, intercept pipeline payloads, and exfiltrate
every secret bound to those pipelines. Models routinely copy the
docs literal `superdupersecret` (or `changeme`, `secret`, etc.)
straight into compose / Dockerfile / k8s output.

Maps to CWE-798 (Use of Hard-coded Credentials) and CWE-521 (Weak
Password Requirements).

## What this catches

| # | Pattern                                                               |
|---|-----------------------------------------------------------------------|
| 1 | `DRONE_RPC_SECRET=<placeholder>` (e.g. `secret`, `changeme`, `superdupersecret`) |
| 2 | `DRONE_RPC_SECRET` shorter than 24 chars                              |
| 3 | `DRONE_RPC_SECRET` with fewer than 8 unique characters (low entropy)  |
| 4 | Repeating-half / single-char-run secrets (`abcabcabc...`, `1111...`)  |

Indirect references such as `${DRONE_RPC_SECRET:?required}` or a
Kubernetes `Secret` carrying a high-entropy value are explicitly
allowed.

## Usage

```bash
python3 detector.py examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. Final
stdout line: `bad=N/N good=0/M PASS|FAIL`.

## Worked example

Run `./run-test.sh` from this directory. It executes the detector
against the bundled samples and asserts `bad=4/4 good=0/4 PASS`.
