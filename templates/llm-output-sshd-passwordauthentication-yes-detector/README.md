# llm-output-sshd-passwordauthentication-yes-detector

Static lint that flags OpenSSH server configuration files
(`sshd_config`, `sshd_config.d/*.conf`) that leave password
authentication enabled — either explicitly (`PasswordAuthentication
yes`), implicitly (no top-level `PasswordAuthentication no` at all,
so the OpenSSH default `yes` applies), or by re-enabling it through
`KbdInteractiveAuthentication` / `ChallengeResponseAuthentication`.

## Why LLMs emit this

The OpenSSH default for `PasswordAuthentication` is `yes`. The
canonical `sshd_config` shipped by every distro keeps that default
commented out, so a "minimal hardened" config that an LLM emits
often *forgets* the line entirely and is therefore wide open to
credential spray. A louder failure mode is when the model writes
`PasswordAuthentication yes` "to make testing easier" or disables
it only inside a `Match User developer` block — the global default
still applies.

A separate trap is the `KbdInteractiveAuthentication` /
`ChallengeResponseAuthentication` pair. Both are `yes` by default
and on a stock PAM stack route straight back to the password
prompt, undoing `PasswordAuthentication no`.

## What it catches

Per file, line-level findings:

- `PasswordAuthentication yes`
- `KbdInteractiveAuthentication yes`
- `ChallengeResponseAuthentication yes`
- `PermitEmptyPasswords yes`

Per file, whole-file finding:

- The file looks like a top-level sshd server config (contains
  `Port`, `ListenAddress`, `HostKey`, `AuthorizedKeysFile`,
  `Subsystem`, or `HostKeyAlgorithms` outside any `Match` block)
  AND it never sets `PasswordAuthentication no` at the top level.
  A `PasswordAuthentication no` that lives only inside a `Match`
  block does NOT count.

## What it does NOT flag

- `PasswordAuthentication no` at top level.
- Drop-in fragments that contain only `Match` blocks and no
  top-level server-identity directives.
- Lines with a trailing `# sshd-pw-ok` comment.
- Files containing `sshd-pw-ok-file` anywhere.

## How to detect

```sh
python3 detector.py path/to/ssh-config-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

```sshd
Port 22
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key
AuthorizedKeysFile .ssh/authorized_keys

PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitEmptyPasswords no
UsePAM yes

Match User ci-bot
    PasswordAuthentication no
    AuthenticationMethods publickey
```

## Refs

- CWE-521: Weak Password Requirements
- CWE-307: Improper Restriction of Excessive Authentication
  Attempts
- CIS Benchmark for Linux — sshd `PasswordAuthentication`
- OpenSSH `sshd_config(5)` — `PasswordAuthentication`,
  `KbdInteractiveAuthentication`, `PermitEmptyPasswords`

## Verify

```sh
bash verify.sh
```

Should print `bad=4/4 good=0/3 PASS`.
