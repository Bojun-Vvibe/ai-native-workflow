# llm-output-clickhouse-default-user-networks-any-detector

Detects LLM-emitted ClickHouse `users.xml` / `users.yaml` configurations that
leave the `default` user (or any active user) with `<networks><ip>` set to a
universally-permissive value — `::/0`, `0.0.0.0/0`, or the legacy bare `::`
— at the network ACL layer. This is orthogonal to the empty-password
problem: even with a password set, exposing the user to the entire IPv4 +
IPv6 space removes one of ClickHouse's primary defense-in-depth layers and
is a common precondition for credential-stuffing and exposed-instance
inventory abuse.

Distinct from `llm-output-clickhouse-default-no-password-detector` (empty
`<password>`). This rule fires on the `<networks>` ACL, which is what
operators reach for first when they want "just let me connect from
anywhere".

## What this catches

| # | Pattern                                                                                          |
|---|--------------------------------------------------------------------------------------------------|
| 1 | `users.xml` `<default>` user with `<networks><ip>::/0</ip></networks>`                            |
| 2 | `users.xml` any active user with `<networks><ip>0.0.0.0/0</ip></networks>`                        |
| 3 | `users.yaml` user block with `networks: { ip: '::/0' }` or `ip: 0.0.0.0/0`                       |
| 4 | `users.xml` with `<networks><host_regex>.*</host_regex></networks>` (regex-as-allowlist abuse)    |

CWE-284 (Improper Access Control). Also overlaps CWE-1188 (Insecure Default
Initialization of Resource) when applied to the `default` user.

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

```
$ ./run-test.sh
BAD  examples/bad/01_users_xml_default_v6_any.xml
BAD  examples/bad/02_users_xml_v4_any.xml
BAD  examples/bad/03_users_yaml_any.yaml
BAD  examples/bad/04_users_xml_host_regex_any.xml
GOOD examples/good/01_users_xml_private_subnet.xml
GOOD examples/good/02_users_yaml_loopback.yaml
GOOD examples/good/03_users_xml_named_host.xml
bad=4/4 good=0/3 PASS
```

## Remediation

- Replace `::/0` and `0.0.0.0/0` with the actual operator subnet
  (`10.0.0.0/8`, `192.168.42.0/24`, etc.).
- Prefer `<host>` (exact DNS name) or a tight CIDR over `<host_regex>`. If
  you must use a regex, anchor it: `^app-[0-9]+\.svc\.local$`.
- Disable the `default` user in production with `<password></password>`
  removed plus `<networks><ip>::1</ip></networks>` so even an exposed port
  can't be used as a stepping stone.
- Combine network ACL with `<password_sha256_hex>` and put the listener
  behind TLS (`<tcp_port_secure>`) and a firewall.
