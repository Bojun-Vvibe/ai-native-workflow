# llm-output-mongodb-bind-ip-all-no-auth-detector

Detects LLM-emitted MongoDB server configurations and launch artifacts that
bind `mongod` to every interface (`bindIp: 0.0.0.0`, `bindIpAll: true`,
`--bind_ip 0.0.0.0`, or `--bind_ip_all`) while leaving authorization
disabled. Public-internet-exposed MongoDB instances without auth have driven
multiple wide-scale ransom waves (`MEOW`, `READ__ME_TO_RECOVER_YOUR_DATA`),
because anyone reaching port 27017 gets unauthenticated `root`-equivalent
access to every database on the server.

## What this catches

| # | Pattern                                                                                          |
|---|--------------------------------------------------------------------------------------------------|
| 1 | `mongod.conf` with `bindIp: 0.0.0.0` (or `bindIpAll: true`) and `security.authorization: disabled` (or no `security:` block at all) |
| 2 | `mongod` CLI invocation with `--bind_ip 0.0.0.0` / `--bind_ip_all` and no `--auth`               |
| 3 | Dockerfile `CMD`/`ENTRYPOINT` running `mongod --bind_ip_all` without `--auth`                    |
| 4 | docker-compose / k8s manifest exposing 27017 on a non-loopback bind without `MONGO_INITDB_ROOT_USERNAME` (i.e., the `mongo` image's auto-auth bootstrap is skipped) |

CWE-306 (Missing Authentication for Critical Function).

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

```
$ ./run-test.sh
BAD  examples/bad/01_mongod_conf_no_auth.yaml
BAD  examples/bad/02_cli_bind_all_no_auth.sh
BAD  examples/bad/03_dockerfile_bind_all.Dockerfile
BAD  examples/bad/04_compose_no_root_user.yml
GOOD examples/good/01_mongod_conf_auth_enabled.yaml
GOOD examples/good/02_cli_loopback_only.sh
GOOD examples/good/03_compose_with_root_user.yml
bad=4/4 good=0/3 PASS
```

## Remediation

- Keep `bindIp: 127.0.0.1` (or a private subnet) until auth + TLS are wired up.
- Set `security.authorization: enabled` in `mongod.conf`, or pass `--auth` on
  the command line.
- For the official `mongo` Docker image, always supply
  `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD` (preferably
  `*_FILE` variants pointing at a secret) before exposing 27017.
- Front the broker with TLS (`net.tls.mode: requireTLS`) and a network policy.
