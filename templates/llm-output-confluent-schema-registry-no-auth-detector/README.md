# llm-output-confluent-schema-registry-no-auth-detector

## Purpose

Flags Confluent Schema Registry server configs (and adjacent client/Compose
files) that leave the REST API open with no authentication. The Schema
Registry REST API can register, evolve, and (with `mode=IMPORT`) silently
replace schemas — anyone who can reach it can poison every consumer in the
cluster. Yet the upstream defaults are happy to bind `0.0.0.0:8081` with
`authentication.method=NONE`, and LLMs frequently propose exactly that when
asked to "make Schema Registry reachable from my CI".

## Signals (any one is sufficient to flag)

1. `authentication.method=NONE` (or `none`, or empty string) on its own line
   in a `.properties`-style config.
2. `listeners=http://0.0.0.0:...` (or `[::]`) in a properties file that does
   *not* also declare `authentication.method=BASIC`.
3. Compose / env-var form `SCHEMA_REGISTRY_AUTHENTICATION_METHOD=NONE`
   (with `:` or `=`, quoted or unquoted).
4. Client-side disablers:
   `basic.auth.credentials.source=` (empty), or
   `schema_registry.basic_auth.enabled=false`.

## How the detector works

`detector.sh` runs targeted `grep -nE` passes per signal and emits one
`FLAG <signal-id> <file>:<lineno> <text>` line per finding. It exits 0
regardless; the caller decides severity.

## False-positive notes

- A `https://...` listener with `authentication.method=BASIC` and a realm
  passes cleanly even if it binds to `0.0.0.0`.
- Loopback-only HTTP listeners pass; the assumption is the operator put an
  authenticating proxy in front.
- Comments quoting the bad strings (`# never set authentication.method=NONE`)
  will be flagged. Keep cautionary docs in prose, not as literal config
  lines.

## Fixtures

- `fixtures/bad/`: 4 files — wildcard listener, explicit `NONE`, Compose
  env, and a client config that disables basic auth.
- `fixtures/good/`: 4 files — properties + Compose with BASIC, loopback
  bind, and a client wired to `USER_INFO`.

## Smoke

```
$ bash smoke.sh
bad=4/4 good=0/4
PASS
```
