# llm-output-redis-acl-default-user-nopass-detector

Detects LLM-emitted Redis 6+ ACL configurations that leave the `default` user
(or any active user) with `nopass` while granting broad command/key access.
This pattern looks "secured" because ACLs are present, but `nopass` means any
client connecting to the listener authenticates as that user with no
credential at all — the network listener is the only access control left.

Distinct from `redis-config-no-requirepass-detector` (which catches missing
legacy `requirepass`) and `redis-protected-mode-no-detector` (which catches
the protected-mode escape hatch). This rule fires on the modern ACL surface:
`aclfile`, inline `user` directives, and `ACL SETUSER` commands.

## What this catches

| # | Pattern                                                                                          |
|---|--------------------------------------------------------------------------------------------------|
| 1 | `redis.conf` `user default on nopass ...` with broad ACL (`~*`, `&*`, `+@all` / `allcommands`)   |
| 2 | Standalone `aclfile` (`users.acl`) with an `on nopass` user that has `~*` and `+@all`            |
| 3 | Bootstrap shell / Dockerfile invoking `redis-cli ACL SETUSER` with `on nopass ~* +@all`          |
| 4 | Any non-disabled user line (`on ... nopass ... +@all`) — even non-`default` — with key wildcard  |

CWE-521 (Weak Password Requirements) — also overlaps CWE-287 (Improper Authentication).

## Usage

```bash
./detector.sh examples/bad/* examples/good/*
```

Exit 0 iff every bad sample fires and zero good samples fire. The trailing
status line is `bad=N/N good=0/M PASS|FAIL`.

## Worked example

```
$ ./run-test.sh
BAD  examples/bad/01_redis_conf_default_nopass.conf
BAD  examples/bad/02_users_acl_nopass.acl
BAD  examples/bad/03_dockerfile_acl_setuser.Dockerfile
BAD  examples/bad/04_alt_user_nopass.conf
GOOD examples/good/01_redis_conf_default_disabled.conf
GOOD examples/good/02_users_acl_password_hash.acl
GOOD examples/good/03_setuser_with_password.sh
bad=4/4 good=0/3 PASS
```

## Remediation

- Disable the `default` user in production: `user default off` (then define
  named users with hashed passwords).
- For each user, store a hashed credential: `>password` for plaintext during
  bootstrap, but prefer `#<sha256-hex>` in committed config.
- Never combine `nopass` with `~*` and `+@all` — if you truly want a no-auth
  read-only probe, scope it: `~probe:* +ping +info -@all`.
- Front the listener with TLS (`tls-port`, `tls-auth-clients yes`) so a
  stolen connection can't bypass identity entirely.
