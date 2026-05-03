# llm-output-rabbitmq-default-guest-credentials-detector

Detects LLM-emitted RabbitMQ broker configurations and launch artifacts that
ship the built-in `guest` / `guest` superuser while exposing AMQP (5672) or the
management plugin (15672) on a non-loopback bind. RabbitMQ ships with a default
`guest` account whose login is silently restricted to `127.0.0.1`; many tutorials
work around the restriction by setting `loopback_users = none` (or
`loopback_users.guest = false`), which re-enables the well-known credential
across the network.

## What this catches

| # | Pattern                                                                                                          |
|---|------------------------------------------------------------------------------------------------------------------|
| 1 | `rabbitmq.conf` containing `loopback_users = none` or `loopback_users.guest = false`                             |
| 2 | `rabbitmq.config` (Erlang term) containing `{loopback_users, []}`                                                |
| 3 | `rabbitmqctl add_user guest guest` or `rabbitmqctl change_password guest guest` invocations                      |
| 4 | docker-compose / k8s / Dockerfile exposing 5672 or 15672 on a non-loopback bind without setting a non-`guest` `RABBITMQ_DEFAULT_USER` (or with `RABBITMQ_DEFAULT_PASS=guest`) |

CWE-798 (Use of Hard-coded Credentials) and CWE-521 (Weak Password Requirements
— the literal documentation default).

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

```
$ ./run-test.sh
BAD  examples/bad/01_loopback_users_none.conf
BAD  examples/bad/02_erlang_loopback_empty.config
BAD  examples/bad/03_add_user_guest.sh
BAD  examples/bad/04_compose_default_pass.yml
GOOD examples/good/01_strong_default_user.yml
GOOD examples/good/02_loopback_only.conf
GOOD examples/good/03_no_loopback_override.conf
bad=4/4 good=0/3 PASS
```

## Why it matters

The `guest` account has the `administrator` tag by default, so any reachable
broker becomes a one-step takeover: list/declare exchanges, drain queues,
shovel messages off-host, or invoke management plugin endpoints to enumerate
internal topology.

## Remediation

- Leave the upstream default in place: `loopback_users.guest = true`.
- Provision a dedicated user (`rabbitmqctl add_user <name> <strong-pw>`),
  tag it appropriately, then `rabbitmqctl delete_user guest`.
- Bind 5672/15672 to `127.0.0.1` (or a private network) until auth is set up.
- In containers, set both `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`
  to non-`guest` values sourced from a secret store, never inline.
