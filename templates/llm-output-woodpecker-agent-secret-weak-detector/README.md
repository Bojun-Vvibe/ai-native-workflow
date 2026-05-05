# llm-output-woodpecker-agent-secret-weak-detector

Detects Woodpecker CI server / agent deployment configurations that
ship the shared agent RPC secret as empty, missing, or set to a
well-known placeholder value.

Woodpecker is a self-hosted, Go-based CI fork of Drone. Server and
agent processes authenticate to each other over gRPC using a single
shared secret named `WOODPECKER_AGENT_SECRET` (older docs:
`WOODPECKER_SECRET`; agent-side: `WOODPECKER_SERVER_SECRET`). If
that secret is empty or weak, anyone reachable on the server's gRPC
port (default `9000`) can register a rogue agent and immediately
start receiving real pipeline work — which routinely contains deploy
keys, cloud credentials, and full repository checkouts.

## Surfaces covered

* `docker-compose.yml` / `compose.yaml` — both list
  (`- WOODPECKER_AGENT_SECRET=...`) and map
  (`WOODPECKER_AGENT_SECRET: ...`) env forms.
* Helm `values.yaml` — `agent.secret`, `server.agent.secret`,
  nested `agent: { secret: ... }`, and `env.WOODPECKER_AGENT_SECRET`.
* Shell / systemd `EnvironmentFile` / `.env` — `KEY=VALUE` pairs,
  with optional `export `.

## What it flags

1. Secret value in the curated weak/placeholder set
   (`changeme`, `secret`, `woodpecker`, `admin`, `<changeme>`,
   `REPLACE_ME`, …).
2. Secret value shorter than 16 characters.
3. Secret key present with empty RHS.
4. `woodpecker-agent` service declared (or `woodpeckerci/...` image
   referenced) but no `WOODPECKER_AGENT_SECRET` set anywhere in the
   file.
5. `WOODPECKER_HOST` / `WOODPECKER_GRPC_ADDR` / `WOODPECKER_SERVER`
   pointed at a non-localhost address with no secret declared.

## Suppression

Add a top-of-file comment:

```
# woodpecker-agent-secret-weak-allowed
```

Use this only for an isolated lab fixture or an integration test.

## CWE refs

* CWE-321: Use of Hard-coded Cryptographic Key
* CWE-798: Use of Hard-coded Credentials
* CWE-1188: Insecure Default Initialization of Resource

## Usage

```
python3 detector.py <path> [<path> ...]
```

Exit code = number of files with at least one finding (capped 255).
Stdout: `<file>:<line>:<reason>`.

## Verify

```
./verify.sh
```

Expected: `bad=4/4 good=0/4 PASS`.
